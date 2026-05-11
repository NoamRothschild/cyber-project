const std = @import("std");
const Io = std.Io;
const net = Io.net;
const linux = std.os.linux;
const IoUring = linux.IoUring;
const createListeningSock = @import("socket.zig").createListeningSock;
const init_ring = @import("socket.zig").init_ring;
const Channel = @import("channel.zig");

const max_connected_clients = 1024;

pub const Server = struct {
    server: net.Server,
    ring: IoUring,
    channels: [max_connected_clients]Channel = undefined,
    free_channels: std.bit_set.ArrayBitSet(usize, max_connected_clients) = .full,
    /// passed into io_uring_copy_cqes
    cqes: [max_connected_clients]linux.io_uring_cqe = undefined,
    gpa: std.mem.Allocator,
    fd_cnt: [1024]usize = std.mem.zeroes([1024]usize),

    pub fn init(alloc: std.mem.Allocator, io: Io, port: u16) !Server {
        return Server{
            .gpa = alloc,
            .server = try createListeningSock(io, port, .ipv4, 1024),
            .ring = try init_ring(max_connected_clients),
        };
    }

    pub fn deinit(self: *Server, io: Io) void {
        self.server.deinit(io);
        self.ring.deinit();
    }

    pub fn run(self: *Server) !void {
        try self.submitAccept();

        while (true) {
            const cqes_read = try self.ring.copy_cqes(self.cqes[0..], 1);
            const cqes = self.cqes[0..@as(usize, cqes_read)];

            for (cqes) |cqe| {
                const channel: *Channel = @ptrFromInt(cqe.user_data);
                switch (channel.type) {
                    .accept => {
                        // std.debug.print("got accept\n", .{});
                        const cli_channel = try self.takeChannel();
                        cli_channel.sock_fd = @bitCast(cqe.res);
                        cli_channel.type = .read;
                        try self.submitRecv(cli_channel);
                    },
                    .read => {
                        if (cqe.res <= 0) { // client disconnected
                            // std.debug.print("client disconnected\n", .{});
                            _ = linux.close(channel.sock_fd);
                            self.returnChannel(&channel);

                            const free_slot_count = self.free_channels.count() + 1;
                            _ = free_slot_count;

                            std.debug.print("\n", .{});
                            return; // FIXME: TEMPORARY
                            // std.debug.print("there are {d} more free slots.\n", .{free_slot_count});
                        } else {
                            var buf = channel.buf.buffer[0..@as(usize, @bitCast(@as(isize, cqe.res)))];
                            while (buf.len > 4) {
                                const len = std.mem.readInt(u32, buf[0..4], .little);
                                if (len + 4 > buf.len)
                                    break;
                                const msg = buf[4 .. len + 4];

                                _ = &msg;
                                // std.debug.print("got message of length {d}: {s}", .{ len, msg });
                                self.fd_cnt[@as(usize, @bitCast(@as(isize, channel.sock_fd)))] += 1;
                                buf = buf[4 + len ..];
                            }

                            if (buf.len != 0)
                                @memmove(channel._buf[0..buf.len], buf[0..]);

                            channel.buf.buffer = channel._buf[buf.len..];
                            try self.submitRecv(channel);
                        }
                    },
                    .write => {},
                }
            }
        }
    }

    pub fn takeChannel(self: *Server) !*Channel {
        if (self.free_channels.findFirstSet()) |idx| {
            self.free_channels.unset(idx);
            const channel = &self.channels[idx];
            channel.buf.buffer = channel._buf[0..];
            return @constCast(channel);
        } else {
            return error.AllChannelsFull;
        }
    }

    pub fn returnChannel(self: *Server, channel: *const *const Channel) void {
        self.free_channels.set(channelIndex(self, channel));
    }

    pub fn channelIndex(self: *const Server, channel: *const *const Channel) usize {
        const start_ptr = &self.channels[0];
        const curr_ptr = channel.*;
        return (@intFromPtr(curr_ptr) - @intFromPtr(start_ptr)) / @sizeOf(Channel);
    }

    pub fn submitAccept(self: *Server) !void {
        const channel: *Channel = try self.takeChannel();
        channel.type = .accept;

        _ = try self.ring.accept_multishot(@as(u64, @intFromPtr(channel)), self.server.socket.handle, null, null, 0);
        // std.debug.assert((try self.ring.submit()) >= 1);
        _ = try self.ring.submit();
    }

    pub fn submitRecv(self: *Server, channel: *Channel) !void {
        channel.type = .read;

        _ = try self.ring.recv(@as(u64, @intFromPtr(channel)), channel.sock_fd, channel.buf, 0);
        // std.debug.assert((try self.ring.submit()) >= 1);
        _ = try self.ring.submit();
    }

    // pub fn submitWrite(self: *Server) void {}
};
