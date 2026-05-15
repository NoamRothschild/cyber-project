const std = @import("std");
const Io = std.Io;
const net = Io.net;
const linux = std.os.linux;
const IoUring = linux.IoUring;
const socket = @import("socket.zig");
const iouring_helpers = @import("uring_helpers.zig");
const Channel = @import("channel.zig");
const Client = @import("../client.zig").Client;
const ConnectionType = @import("../client.zig").ConnectionType;
const ChannelManager = @import("channel_manager.zig").ChannelManager;
const ClientContainer = @import("client_manager.zig").ClientContainer;
const Node = @import("../node/node.zig");
const protocol = @import("protocol.zig");

const max_connected_clients = 1024;
const cqes_capacity = 1024;

pub const Server = struct {
    tcp_server: net.Server,
    udp_server: net.Socket,
    ring: IoUring,
    channel_manager: ChannelManager(cqes_capacity),
    clients: ClientContainer(max_connected_clients),
    udp_channel: *Channel,
    /// passed into io_uring_copy_cqes
    cqes: [cqes_capacity]linux.io_uring_cqe = undefined,
    gpa: std.mem.Allocator,
    node: Node,

    pub fn init(self: *Server, alloc: std.mem.Allocator, io: Io, port: u16) !void {
        _ = port;
        var tcp_server = try socket.socket(io, 8085, .ipv4, .tcp, 1024);
        errdefer tcp_server.deinit(io);
        var udp_server = try socket.socket(io, 8086, .ipv4, .udp, null);
        errdefer udp_server.close(io);
        var ring = try iouring_helpers.init_ring(cqes_capacity);
        errdefer ring.deinit();

        self.* = .{
            .gpa = alloc,
            .tcp_server = tcp_server,
            .udp_server = udp_server,
            .ring = ring,
            .channel_manager = .init(),
            .clients = .init,
            .udp_channel = undefined,
            .cqes = undefined,
            .node = .init(alloc, self),
        };

        const udp_channel = try self.channel_manager.takeChannel();
        udp_channel.resetForUdpRead(self.udp_server.handle);
        self.udp_channel = udp_channel;
    }

    pub fn deinit(self: *Server, io: Io) void {
        self.tcp_server.deinit(io);
        self.udp_server.close(io);
        self.ring.deinit();
        self.node.deinit();
    }

    pub fn run(self: *Server, io: Io) !void {
        try self.submitAccept();
        try self.submitUdpRecv();

        while (true) {
            const cqes_read = try self.ring.copy_cqes(self.cqes[0..], 1);
            const cqes = self.cqes[0..@as(usize, cqes_read)];

            for (cqes) |cqe| {
                self.handleCqe(io, cqe) catch |err| {
                    std.debug.print("error handling cqe: {}\n", .{err});
                };
            }
        }
    }

    pub fn handleCqe(self: *Server, io: Io, cqe: linux.io_uring_cqe) !void {
        const channel: *Channel = @ptrFromInt(cqe.user_data);
        switch (channel.type) {
            .accept => {
                if (cqe.res < 0) return;
                const fd: std.posix.fd_t = @intCast(cqe.res);
                const cli_channel = try self.channel_manager.takeChannel();
                cli_channel.resetForTcpRead(fd, null);
                try self.submitTcpRecv(cli_channel);
            },
            .tcp_read => {
                if (channel.sock_fd < 0) return;
                if (cqe.res <= 0) {
                    try self.handleDisconnect(channel);
                    return;
                }
                try self.handleTcpRecv(io, channel, @intCast(cqe.res));
            },
            .tcp_write => {
                if (channel.sock_fd < 0) return;
                if (cqe.res <= 0) {
                    try self.handleDisconnect(channel);
                    return;
                }
                const written: usize = @intCast(cqe.res);
                channel.write_off += written;
                if (channel.write_off < channel.write_len) {
                    try self.submitTcpSend(channel);
                } else {
                    const slot = channel.write_client_slot orelse return error.MissingWriteSlot;
                    const client = &(self.clients.at(slot).client orelse return);
                    _ = client.popOutbound();
                    self.clients.at(slot).in_flight = false;
                    channel.write_client_slot = null;
                    try self.submitTcpRecv(channel);
                    try self.kickClientWriter(slot);
                }
            },
            .udp_read => {
                if (cqe.res > 0) {
                    const bytes_read: usize = @intCast(cqe.res);
                    const msg = channel.read_buf[0..bytes_read];
                    try self.handleUdpDatagram(io, channel, msg);
                }
                if (channel.type == .udp_read) {
                    try self.submitUdpRecvOn(channel);
                }
            },
            .udp_write => {
                if (cqe.res < 0) {
                    if (channel.write_client_slot) |slot| {
                        self.clients.at(slot).in_flight = false;
                        channel.write_client_slot = null;
                    }
                    channel.type = .udp_read;
                    try self.submitUdpRecvOn(channel);
                    return;
                }
                const slot = channel.write_client_slot orelse return error.MissingWriteSlot;
                const client = &(self.clients.at(slot).client orelse return);
                _ = client.popOutbound();
                self.clients.at(slot).in_flight = false;
                channel.write_client_slot = null;
                channel.type = .udp_read;
                try self.submitUdpRecvOn(channel);
                try self.kickPendingWriters();
            },
        }
    }

    pub fn handleTcpRecv(self: *Server, io: Io, channel: *Channel, bytes_read: usize) !void {
        channel.read_used += bytes_read;
        var cursor: usize = 0;
        while (channel.read_used - cursor >= protocol.frame_header_len) {
            const msg_len = try protocol.length(channel.read_buf[cursor..]);
            const total = protocol.frame_header_len + msg_len;
            if (channel.read_used - cursor < total)
                break;

            const msg = channel.read_buf[cursor + protocol.frame_header_len .. cursor + total];
            try self.handleTcpMessage(io, channel, msg);
            cursor += total;
        }
        const left = channel.read_used - cursor;
        if (left > 0 and cursor > 0) {
            @memmove(channel.read_buf[0..left], channel.read_buf[cursor .. cursor + left]);
        }
        channel.read_used = left;
        // If message handling scheduled a write, keep this channel on write path.
        if (channel.type == .tcp_read) {
            try self.submitTcpRecv(channel);
        }
    }

    pub fn handleDisconnect(self: *Server, channel: *Channel) !void {
        if (channel.sock_fd < 0) return;
        std.debug.print("client disconnected.\n", .{});
        if (channel.client_slot) |slot| {
            if (self.clients.at(slot).client) |cli| {
                self.node.grid.remove(cli.grid_uid, cli.game_state.cell_x(), cli.game_state.cell_y()) catch {};
                _ = self.node.clients.remove(cli.client_id);
            }
            self.clients.returnClientSlot(slot);
        }
        _ = linux.close(channel.sock_fd);
        channel.sock_fd = -1;
        channel.client_slot = null;
        channel.write_client_slot = null;
        self.channel_manager.returnChannel(channel);
    }

    pub fn submitAccept(self: *Server) !void {
        const channel: *Channel = try self.channel_manager.takeChannel();
        channel.resetForAccept();

        _ = try self.ring.accept_multishot(@as(u64, @intFromPtr(channel)), self.tcp_server.socket.handle, null, null, 0);
        _ = try self.ring.submit();
    }

    pub fn submitUdpRecv(self: *Server) !void {
        try self.submitUdpRecvOn(self.udp_channel);
    }

    fn submitUdpRecvOn(self: *Server, channel: *Channel) !void {
        channel.type = .udp_read;
        channel.setupUdpRecvMsg();
        _ = try self.ring.recvmsg(@as(u64, @intFromPtr(channel)), channel.sock_fd, &channel.udp_recv_msghdr, 0);
        _ = try self.ring.submit();
    }

    fn submitTcpRecv(self: *Server, channel: *Channel) !void {
        channel.type = .tcp_read;
        if (channel.read_used >= channel.read_buf.len) return error.RecvBufferFull;
        _ = try self.ring.recv(
            @as(u64, @intFromPtr(channel)),
            channel.sock_fd,
            .{ .buffer = channel.read_buf[channel.read_used..] },
            0,
        );
        _ = try self.ring.submit();
    }

    fn submitTcpSend(self: *Server, channel: *Channel) !void {
        channel.type = .tcp_write;
        _ = try self.ring.send(
            @as(u64, @intFromPtr(channel)),
            channel.sock_fd,
            channel.write_buf[channel.write_off..channel.write_len],
            0,
        );
        _ = try self.ring.submit();
    }

    fn submitUdpSend(self: *Server, channel: *Channel) !void {
        channel.type = .udp_write;
        channel.setupUdpSendMsg();
        _ = try self.ring.sendmsg(@as(u64, @intFromPtr(channel)), channel.sock_fd, &channel.udp_send_msghdr, 0);
        _ = try self.ring.submit();
    }

    fn handleTcpMessage(self: *Server, io: Io, channel: *Channel, payload: []const u8) !void {
        const slot = channel.client_slot orelse {
            const new_slot = try self.clients.takeClientSlot();
            self.clients.at(new_slot).client = try Client.initTcp(self.gpa, new_slot, payload);
            const cli: *Client = &self.clients.at(new_slot).client.?;

            try self.node.clients.put(self.gpa, cli.client_id, &self.clients.at(new_slot).client.?);
            cli.grid_uid = try self.node.grid.add(
                self.gpa,
                .{ .client = @ptrCast(&self.clients.at(new_slot).client) },
                cli.game_state.cell_x(),
                cli.game_state.cell_y(),
                null,
                null,
                null,
            );

            channel.client_slot = new_slot;
            self.clients.at(new_slot).tcp_channel_idx = self.channel_manager.channelIndex(channel);

            try self.kickClientWriter(new_slot);
            return;
        };

        const client = &(self.clients.at(slot).client orelse return);

        client.onRecvMessage(self.gpa, &self.node, io, .tcp, payload);
        try self.enqueueOutboundWithRetry(slot, .tcp, payload);
        try self.kickClientWriter(slot);
    }

    fn handleUdpDatagram(self: *Server, io: Io, channel: *Channel, datagram: []const u8) !void {
        if (datagram.len < protocol.frame_header_len)
            return;

        const msg_len = try protocol.length(datagram);
        const total = protocol.frame_header_len + msg_len;
        if (datagram.len != total)
            return error.MessageInvalidLength;

        const payload = datagram[protocol.frame_header_len..total];
        const slot = if (self.clients.findClientByUdpPeer(&channel.udp_peer_addr, channel.udp_peer_addr_len)) |bound_slot|
            bound_slot
        else { // handshake
            const user_id = try Client.initUdp(self, payload);
            const join_slot = self.clients.findClientByUserId(user_id) orelse return;
            self.clients.at(join_slot).udp_peer_known = true;
            self.clients.at(join_slot).udp_peer_addr = channel.udp_peer_addr;
            self.clients.at(join_slot).udp_peer_len = channel.udp_peer_addr_len;

            try self.kickClientWriter(join_slot);
            return;
        };

        const client = &(self.clients.at(slot).client orelse return);

        client.onRecvMessage(self.gpa, &self.node, io, .udp, payload);
        try self.enqueueOutboundWithRetry(slot, .udp, payload);

        try self.kickClientWriter(slot);
    }

    fn enqueueOutboundWithRetry(self: *Server, slot: usize, conn_t: ConnectionType, payload: []const u8) !void {
        var retries: usize = 0;
        while (true) {
            const client = &(self.clients.at(slot).client orelse return error.ClientMissing);
            client.enqueueOutbound(conn_t, payload) catch |err| switch (err) {
                error.WouldBlock => {
                    try self.kickClientWriter(slot);
                    retries += 1;
                    // TODO: switch this retry/yield path to a normal syscall-backed wait strategy.
                    if (retries >= 16) return error.WouldBlock;
                    std.Thread.yield() catch {};
                    continue;
                },
                else => return err,
            };
            return;
        }
    }

    pub fn kickPendingWriters(self: *Server) !void {
        for (self.clients.raw, 0..) |slot_state, slot| {
            if (slot_state.client != null) try self.kickClientWriter(slot);
        }
    }

    pub fn kickClientWriter(self: *Server, slot: usize) !void {
        if (self.clients.at(slot).in_flight) return;
        const client = &(self.clients.at(slot).client orelse return);
        const next = client.peekOutbound() orelse return;
        switch (next.conn) {
            .tcp => {
                const channel_idx = self.clients.at(slot).tcp_channel_idx orelse return;
                const channel = self.channel_manager.get(channel_idx);
                try protocol.prepareFramedMessage(channel.write_buf[0..], next.payload);
                channel.write_len = protocol.frame_header_len + next.payload.len;
                channel.write_off = 0;
                channel.write_client_slot = slot;
                self.clients.at(slot).in_flight = true;
                try self.submitTcpSend(channel);
            },
            .udp => {
                if (!self.clients.at(slot).udp_peer_known) return;
                const channel = self.udp_channel;
                if (channel.type != .udp_read) return;
                try protocol.prepareFramedMessage(channel.write_buf[0..], next.payload);
                channel.write_len = protocol.frame_header_len + next.payload.len;
                channel.write_off = 0;
                channel.write_client_slot = slot;
                channel.udp_peer_addr = self.clients.at(slot).udp_peer_addr;
                channel.udp_peer_addr_len = self.clients.at(slot).udp_peer_len;
                self.clients.at(slot).in_flight = true;
                try self.submitUdpSend(channel);
            },
        }
    }
};

fn parseUserId(payload: []const u8) !usize {
    return std.fmt.parseInt(usize, payload, 10);
}
