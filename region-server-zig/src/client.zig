const std = @import("std");
const Io = std.Io;

pub const ConnectionType = enum { tcp, udp };
pub const max_payload_len: usize = 512;
pub const outbound_queue_capacity: usize = 64;

pub const OutboundView = struct {
    conn: ConnectionType,
    payload: []const u8,
};

pub const Client = struct {
    const Self = @This();
    const OutboundMessage = struct {
        conn: ConnectionType,
        len: usize,
        payload: [max_payload_len]u8,
    };

    client_id: usize,
    udp_extension_joined: bool = false,
    outbound_head: usize = 0,
    outbound_len: usize = 0,
    outbound_queue: [outbound_queue_capacity]OutboundMessage = undefined,

    pub fn init(cli_id: usize) Self {
        var self: Self = .{
            .client_id = cli_id,
        };
        for (&self.outbound_queue) |*item| {
            item.* = .{
                .conn = .tcp,
                .len = 0,
                .payload = undefined,
            };
        }
        return self;
    }

    pub fn onRecvMessage(self: *Self, io: Io, conn_t: ConnectionType, data: []const u8) void {
        std.debug.print("on {s} got: {s}\n", .{ @tagName(conn_t), data });
        _ = self;
        _ = io;
    }

    pub fn handleHandshake(self: *Self, conn_t: ConnectionType, data: []const u8) !void {
        if (conn_t == .udp and self.udp_extension_joined) return error.AlreadyJoined;
        _ = data;
        const suffix = switch (conn_t) {
            .tcp => "OK",
            .udp => "JOIN_OK",
        };
        var payload: [max_payload_len]u8 = undefined;
        const payload_len: usize = 4 + suffix.len;
        if (payload_len > payload.len) return error.MessageTooLong;
        @memset(payload[0..4], 0);
        @memcpy(payload[4 .. 4 + suffix.len], suffix);

        switch (conn_t) {
            .tcp => {
                self.udp_extension_joined = false;
                try self.enqueueOutbound(.tcp, payload[0..payload_len]);
            },
            .udp => {
                self.udp_extension_joined = true;
                errdefer self.udp_extension_joined = false;
                try self.enqueueOutbound(.udp, payload[0..payload_len]);
            },
        }
    }

    pub fn queueEcho(self: *Self, conn_t: ConnectionType, payload: []const u8) !void {
        try self.enqueueOutbound(conn_t, payload);
    }

    pub fn canEnqueue(self: *const Self) bool {
        return self.outbound_len < outbound_queue_capacity;
    }

    pub fn enqueueOutbound(self: *Self, conn_t: ConnectionType, payload: []const u8) !void {
        switch (conn_t) {
            .tcp => {},
            .udp => if (!self.udp_extension_joined) return error.UdpNotJoined,
        }
        if (payload.len > max_payload_len) return error.MessageTooLong;
        if (!self.canEnqueue()) return error.WouldBlock;

        const idx = (self.outbound_head + self.outbound_len) % outbound_queue_capacity;
        var msg = &self.outbound_queue[idx];
        msg.conn = conn_t;
        msg.len = payload.len;
        @memcpy(msg.payload[0..payload.len], payload);
        self.outbound_len += 1;
    }

    pub fn peekOutbound(self: *const Self) ?OutboundView {
        if (self.outbound_len == 0) return null;
        const msg = &self.outbound_queue[self.outbound_head];
        return .{
            .conn = msg.conn,
            .payload = msg.payload[0..msg.len],
        };
    }

    pub fn popOutbound(self: *Self) ?void {
        if (self.outbound_len == 0) return null;
        self.outbound_head = (self.outbound_head + 1) % outbound_queue_capacity;
        self.outbound_len -= 1;
        return {};
    }

    pub fn hasUdp(self: *const Self) bool {
        return self.udp_extension_joined;
    }
};
