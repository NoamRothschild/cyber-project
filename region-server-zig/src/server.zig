const std = @import("std");
const Io = std.Io;
const net = Io.net;
const linux = std.os.linux;
const IoUring = linux.IoUring;
const createListeningSock = @import("socket.zig").createListeningSock;
const createUDPListeningSock = @import("socket.zig").createUDPListeningSock;
const init_ring = @import("socket.zig").init_ring;
const Channel = @import("channel.zig");
const Client = @import("client.zig").Client;
const ConnectionType = @import("client.zig").ConnectionType;
const max_payload_len = @import("client.zig").max_payload_len;

const max_connected_clients = 1024;
const frame_header_len = 4;
const max_frame_len = frame_header_len + max_payload_len;

pub const Server = struct {
    const ClientSlot = struct {
        client: ?Client = null,
        in_flight: bool = false,
        tcp_channel_idx: ?usize = null,
        udp_peer_known: bool = false,
        udp_peer_addr: linux.sockaddr.storage = std.mem.zeroes(linux.sockaddr.storage),
        udp_peer_len: linux.socklen_t = @sizeOf(linux.sockaddr.storage),
    };

    tcp_server: net.Server,
    udp_server: net.Socket,
    ring: IoUring,
    channels: [max_connected_clients]Channel = undefined,
    free_channels: std.bit_set.ArrayBitSet(usize, max_connected_clients) = .full,
    clients: [max_connected_clients]ClientSlot = [_]ClientSlot{.{}} ** max_connected_clients,
    udp_channel_idx: ?usize = null,
    /// passed into io_uring_copy_cqes
    cqes: [max_connected_clients]linux.io_uring_cqe = undefined,
    gpa: std.mem.Allocator,

    pub fn init(self: *Server, alloc: std.mem.Allocator, io: Io, port: u16) !void {
        var tcp_server = try createListeningSock(io, port, .ipv4, 1024);
        errdefer tcp_server.deinit(io);
        var udp_server = try createUDPListeningSock(io, port, .ipv4);
        errdefer udp_server.close(io);
        var ring = try init_ring(max_connected_clients);
        errdefer ring.deinit();

        self.* = .{
            .gpa = alloc,
            .tcp_server = tcp_server,
            .udp_server = udp_server,
            .ring = ring,
            .channels = undefined,
            .free_channels = .full,
            .clients = [_]ClientSlot{.{}} ** max_connected_clients,
            .udp_channel_idx = null,
            .cqes = undefined,
        };
        for (&self.channels) |*channel| channel.* = .{};
    }

    pub fn deinit(self: *Server, io: Io) void {
        self.tcp_server.deinit(io);
        self.udp_server.close(io);
        self.ring.deinit();
    }

    pub fn run(self: *Server) !void {
        try self.submitAccept();
        try self.submitUdpRecv();

        while (true) {
            const cqes_read = try self.ring.copy_cqes(self.cqes[0..], 1);
            const cqes = self.cqes[0..@as(usize, cqes_read)];

            for (cqes) |cqe| {
                self.handleCqe(cqe) catch |err| {
                    std.debug.print("error handling cqe: {}\n", .{err});
                };
            }
        }
    }

    pub fn handleCqe(self: *Server, cqe: linux.io_uring_cqe) !void {
        const channel: *Channel = @ptrFromInt(cqe.user_data);
        switch (channel.type) {
            .accept => {
                if (cqe.res < 0) return;
                const fd: std.posix.fd_t = @intCast(cqe.res);
                const cli_channel = try self.takeChannel();
                cli_channel.resetForTcpRead(fd, null);
                try self.submitTcpRecv(cli_channel);
            },
            .tcp_read => {
                if (cqe.res <= 0) {
                    std.debug.print("client disconnected.\n", .{});
                    if (channel.client_slot) |slot| self.clearClientState(slot);
                    _ = linux.close(channel.sock_fd);
                    self.returnChannel(channel);
                    return;
                }
                try self.handleTcpRecv(channel, @intCast(cqe.res));
            },
            .tcp_write => {
                if (cqe.res < 0) {
                    std.debug.print("client disconnected.\n", .{});
                    if (channel.client_slot) |slot| self.clearClientState(slot);
                    _ = linux.close(channel.sock_fd);
                    self.returnChannel(channel);
                    return;
                }
                const written: usize = @intCast(cqe.res);
                channel.write_off += written;
                if (channel.write_off < channel.write_len) {
                    try self.submitTcpSend(channel);
                } else {
                    const slot = channel.write_client_slot orelse return error.MissingWriteSlot;
                    const client = &(self.clients[slot].client orelse return);
                    _ = client.popOutbound();
                    self.clients[slot].in_flight = false;
                    channel.write_client_slot = null;
                    try self.submitTcpRecv(channel);
                    try self.kickClientWriter(slot);
                }
            },
            .udp_read => {
                if (cqe.res > 0) {
                    const bytes_read: usize = @intCast(cqe.res);
                    const msg = channel.read_buf[0..bytes_read];
                    try self.handleUdpDatagram(channel, msg);
                }
                if (channel.type == .udp_read) {
                    try self.submitUdpRecvOn(channel);
                }
            },
            .udp_write => {
                if (cqe.res < 0) {
                    if (channel.write_client_slot) |slot| {
                        self.clients[slot].in_flight = false;
                        channel.write_client_slot = null;
                    }
                    channel.type = .udp_read;
                    try self.submitUdpRecvOn(channel);
                    return;
                }
                const slot = channel.write_client_slot orelse return error.MissingWriteSlot;
                const client = &(self.clients[slot].client orelse return);
                _ = client.popOutbound();
                self.clients[slot].in_flight = false;
                channel.write_client_slot = null;
                channel.type = .udp_read;
                try self.submitUdpRecvOn(channel);
                try self.kickPendingWriters();
            },
        }
    }

    pub fn handleTcpRecv(self: *Server, channel: *Channel, bytes_read: usize) !void {
        channel.read_used += bytes_read;
        var cursor: usize = 0;
        while (channel.read_used - cursor >= frame_header_len) {
            const len_buf: *const [4]u8 = @ptrCast(channel.read_buf[cursor .. cursor + frame_header_len]);
            const msg_len = std.mem.readInt(u32, len_buf, .little);
            if (msg_len > max_payload_len) return error.MessageTooLarge;
            const total = frame_header_len + msg_len;
            if (channel.read_used - cursor < total) break;
            const msg = channel.read_buf[cursor + frame_header_len .. cursor + total];
            try self.handleTcpMessage(channel, msg);
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

    pub fn takeChannel(self: *Server) !*Channel {
        if (self.free_channels.findFirstSet()) |idx| {
            self.free_channels.unset(idx);
            return &self.channels[idx];
        } else {
            return error.AllChannelsFull;
        }
    }

    pub fn returnChannel(self: *Server, channel: *Channel) void {
        self.free_channels.set(channelIndex(self, channel));
    }

    pub fn channelIndex(self: *const Server, channel: *const Channel) usize {
        const start_ptr = &self.channels[0];
        const curr_ptr = channel;
        return (@intFromPtr(curr_ptr) - @intFromPtr(start_ptr)) / @sizeOf(Channel);
    }

    pub fn submitAccept(self: *Server) !void {
        const channel: *Channel = try self.takeChannel();
        channel.resetForAccept();

        _ = try self.ring.accept_multishot(@as(u64, @intFromPtr(channel)), self.tcp_server.socket.handle, null, null, 0);
        _ = try self.ring.submit();
    }

    pub fn submitUdpRecv(self: *Server) !void {
        const channel: *Channel = try self.takeChannel();
        channel.resetForUdpRead(self.udp_server.handle);
        self.udp_channel_idx = self.channelIndex(channel);
        try self.submitUdpRecvOn(channel);
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

    fn handleTcpMessage(self: *Server, channel: *Channel, payload: []const u8) !void {
        const existing_slot = channel.client_slot;
        const slot = existing_slot orelse blk: {
            const user_id = try parseUserId(payload);
            const new_slot = try self.takeClientSlot();
            self.clients[new_slot].client = Client.init(user_id);
            channel.client_slot = new_slot;
            self.clients[new_slot].tcp_channel_idx = self.channelIndex(channel);
            break :blk new_slot;
        };

        const client = &(self.clients[slot].client orelse return);
        client.onRecvMessage(undefined, .tcp, payload);

        if (existing_slot == null)
            try client.handleHandshake(.tcp, payload)
        else
            try self.enqueueOutboundWithRetry(slot, .tcp, payload);
        try self.kickClientWriter(slot);
    }

    fn handleUdpDatagram(self: *Server, channel: *Channel, datagram: []const u8) !void {
        if (datagram.len < frame_header_len)
            return;

        const len_buf: *const [4]u8 = @ptrCast(datagram[0..frame_header_len]);
        const msg_len = std.mem.readInt(u32, len_buf, .little);
        if (msg_len > max_payload_len)
            return error.MessageTooLarge;

        const total = frame_header_len + msg_len;
        if (datagram.len != total)
            return error.MessageInvalidLength;

        const payload = datagram[frame_header_len..total];
        const slot = if (self.findClientByUdpPeer(&channel.udp_peer_addr, channel.udp_peer_addr_len)) |bound_slot|
            bound_slot
        else blk: { // handshake
            const user_id = parseUserId(payload) catch return;
            const join_slot = self.findClientByUserId(user_id) orelse return;
            self.clients[join_slot].udp_peer_known = true;
            self.clients[join_slot].udp_peer_addr = channel.udp_peer_addr;
            self.clients[join_slot].udp_peer_len = channel.udp_peer_addr_len;
            break :blk join_slot;
        };

        const client = &(self.clients[slot].client orelse return);
        client.onRecvMessage(undefined, .udp, payload);

        if (!client.hasUdp())
            try client.handleHandshake(.udp, payload)
        else
            try self.enqueueOutboundWithRetry(slot, .udp, payload);

        try self.kickClientWriter(slot);
    }

    fn enqueueOutboundWithRetry(self: *Server, slot: usize, conn_t: ConnectionType, payload: []const u8) !void {
        var retries: usize = 0;
        while (true) {
            const client = &(self.clients[slot].client orelse return error.ClientMissing);
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

    fn kickPendingWriters(self: *Server) !void {
        for (self.clients, 0..) |slot_state, slot| {
            if (slot_state.client != null) try self.kickClientWriter(slot);
        }
    }

    fn kickClientWriter(self: *Server, slot: usize) !void {
        if (self.clients[slot].in_flight) return;
        const client = &(self.clients[slot].client orelse return);
        const next = client.peekOutbound() orelse return;
        switch (next.conn) {
            .tcp => {
                const channel_idx = self.clients[slot].tcp_channel_idx orelse return;
                const channel = &self.channels[channel_idx];
                try prepareFramedMessage(channel.write_buf[0..], next.payload);
                channel.write_len = frame_header_len + next.payload.len;
                channel.write_off = 0;
                channel.write_client_slot = slot;
                self.clients[slot].in_flight = true;
                try self.submitTcpSend(channel);
            },
            .udp => {
                if (!self.clients[slot].udp_peer_known) return;
                const channel_idx = self.udp_channel_idx orelse return;
                const channel = &self.channels[channel_idx];
                if (channel.type != .udp_read) return;
                try prepareFramedMessage(channel.write_buf[0..], next.payload);
                channel.write_len = frame_header_len + next.payload.len;
                channel.write_off = 0;
                channel.write_client_slot = slot;
                channel.udp_peer_addr = self.clients[slot].udp_peer_addr;
                channel.udp_peer_addr_len = self.clients[slot].udp_peer_len;
                self.clients[slot].in_flight = true;
                try self.submitUdpSend(channel);
            },
        }
    }

    fn clearClientState(self: *Server, slot: usize) void {
        self.clients[slot] = .{};
    }

    fn takeClientSlot(self: *Server) !usize {
        for (self.clients, 0..) |slot_state, i| {
            if (slot_state.client == null) return i;
        }
        return error.ClientsFull;
    }

    fn findClientByUserId(self: *Server, user_id: usize) ?usize {
        for (self.clients, 0..) |slot_state, i| {
            if (slot_state.client) |c| {
                if (c.client_id == user_id) return i;
            }
        }
        return null;
    }

    fn findClientByUdpPeer(self: *const Server, peer_addr: *const linux.sockaddr.storage, peer_len: linux.socklen_t) ?usize {
        for (self.clients, 0..) |slot_state, i| {
            if (!slot_state.udp_peer_known) continue;
            if (udpPeerEq(&slot_state.udp_peer_addr, slot_state.udp_peer_len, peer_addr, peer_len)) return i;
        }
        return null;
    }
};

fn parseUserId(payload: []const u8) !usize {
    return std.fmt.parseInt(usize, payload, 10);
}

fn buildHandshakePayload(buf: []u8, suffix: []const u8) ![]const u8 {
    const needed = frame_header_len + suffix.len;
    if (needed > buf.len) return error.MessageTooLarge;
    @memset(buf[0..frame_header_len], 0);
    @memcpy(buf[frame_header_len .. frame_header_len + suffix.len], suffix);
    return buf[0..needed];
}

fn prepareFramedMessage(buf: []u8, payload: []const u8) !void {
    if (payload.len > max_payload_len) return error.MessageTooLarge;
    const total = frame_header_len + payload.len;
    if (total > buf.len) return error.MessageTooLarge;
    const len_buf: *[4]u8 = @ptrCast(buf[0..frame_header_len]);
    std.mem.writeInt(u32, len_buf, @intCast(payload.len), .little);
    @memcpy(buf[frame_header_len..total], payload);
}

fn udpPeerEq(a_addr: *const linux.sockaddr.storage, a_len: linux.socklen_t, b_addr: *const linux.sockaddr.storage, b_len: linux.socklen_t) bool {
    if (a_len != b_len) return false;
    if (a_addr.family != b_addr.family) return false;
    const len: usize = @intCast(a_len);
    const a_bytes = std.mem.asBytes(a_addr);
    const b_bytes = std.mem.asBytes(b_addr);
    return std.mem.eql(u8, a_bytes[0..len], b_bytes[0..len]);
}
