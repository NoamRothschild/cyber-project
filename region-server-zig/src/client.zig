const std = @import("std");
const proto = @import("proto/game/region.pb.zig");
const Io = std.Io;
const Allocator = std.mem.Allocator;

const grid = @import("node/grid.zig");
const Node = @import("node/node.zig");

const view_threshold = 1.5;
pub const view_width_px: comptime_int = @floor(1500 * view_threshold);
pub const view_height_px: comptime_int = @floor(750 * view_threshold);

pub const view_width_cells = view_width_px / grid.cell_size;
pub const view_height_cells = view_height_px / grid.cell_size;

pub const ConnectionType = enum { tcp, udp };
pub const outbound_queue_capacity: usize = 64;
const max_payload_len = @import("net/protocol.zig").max_payload_len;

pub const OutboundView = struct {
    conn: ConnectionType,
    payload: []const u8,
};

pub const ClientId = usize;

pub const Client = struct {
    const Self = @This();
    const OutboundMessage = struct {
        conn: ConnectionType,
        len: usize,
        payload: [max_payload_len]u8,
    };

    client_id: ClientId,
    game_state: GameState,
    grid_uid: usize = 0,
    udp_extension_joined: bool = false,
    outbound_head: usize = 0,
    outbound_len: usize = 0,
    outbound_queue: [outbound_queue_capacity]OutboundMessage = undefined,

    pub fn init(alloc: Allocator, cli_id: ClientId, node: *Node) error{OutOfMemory}!Self {
        var self: Self = .{
            .client_id = cli_id,
            .game_state = .{},
        };
        for (&self.outbound_queue) |*item| {
            item.* = .{
                .conn = .tcp,
                .len = 0,
                .payload = undefined,
            };
        }

        self.grid_uid = try node.grid.add(
            alloc,
            .{ .client = .{ .cli_id = cli_id } },
            self.game_state.cell_x(),
            self.game_state.cell_y(),
            null,
            null,
            null,
        );
        return self;
    }

    pub fn onRecvMessage(self: *Self, alloc: Allocator, node: *Node, io: Io, conn_t: ConnectionType, data: []const u8) void {
        // std.debug.print("on {s} got: {s}\n", .{ @tagName(conn_t), data });
        _ = conn_t;
        _ = io;
        var reader = Io.Reader.fixed(data);
        const update = proto.RegionUpdate.decode(&reader, alloc) catch |err| {
            std.log.warn("failed to parse packet from client {d}: {s}\n", .{ self.client_id, @errorName(err) });
            return;
        };
        if (update.payload == null) {
            std.log.warn("failed to parse packet from client {d}: payload field not found\n", .{self.client_id});
            return;
        }
        switch (update.payload.?) {
            .location_block => |ev| {
                if (self.game_state.moved_cell(toUsize(ev.x), toUsize(ev.y))) {
                    const old_cx = self.game_state.cell_x();
                    const old_cy = self.game_state.cell_y();
                    self.game_state.x = toUsize(ev.x);
                    self.game_state.y = toUsize(ev.y);
                    node.grid.move(
                        alloc,
                        self.grid_uid,
                        old_cx,
                        old_cy,
                        self.game_state.cell_x(),
                        self.game_state.cell_y(),
                    ) catch |err| switch (err) {
                        error.NotFound => unreachable,
                        else => @panic("moving client on grid failed."),
                    };

                    std.debug.print("moved cell\n", .{});
                }
                std.debug.print("got movement packet: {}\n", .{ev});
            },
            // .bullet_shot,
            // .potion_use,
            // .item_drop,
            // .item_pickup,
            // .shop_buy,
            // .reload_act,
            // .moved_server,
            else => {},
        }
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
                std.debug.print("user {d} joined\n", .{self.client_id});
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
        if (conn_t == .udp and !self.udp_extension_joined)
            return error.UdpNotJoined;
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

pub const GameState = struct {
    x: usize = 350, // FIXME: TEMPORARY VALUE
    y: usize = 350, // FIXME: TEMPORARY VALUE
    hp: usize = 100,
    money: usize = 100,

    pub inline fn cell_x(self: *const GameState) usize {
        return self.x / grid.cell_size;
    }

    pub inline fn cell_y(self: *const GameState) usize {
        return self.y / grid.cell_size;
    }

    pub fn moved_cell(self: *const GameState, new_x: usize, new_y: usize) bool {
        return ((new_x / grid.cell_size) != self.cell_x() or (new_y / grid.cell_size) != self.cell_y());
    }
};

fn toUsize(v: i32) usize {
    return @as(usize, @as(u32, @bitCast(v)));
}
