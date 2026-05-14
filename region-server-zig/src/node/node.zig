const std = @import("std");
const Allocator = std.mem.Allocator;

const Grid = @import("grid.zig");
const Server = @import("../net/server.zig").Server;
const client = @import("../client.zig");
const proto = @import("../proto/game/region.pb.zig");
const Node = @This();
const buildServerResponsePayload = @import("../net/protocol.zig").buildServerResponsePayload;

// NOTE: one node now holds the same space as all old nodes (the whole map)
pub const width = 4600 * 17;
pub const height = 2200 * 20;

grid: Grid,
clients: std.AutoHashMapUnmanaged(client.ClientId, *client.Client),
alloc: Allocator,
server: *Server, // NOTE: might remove it in the future, idk what I feel abt that
// enemy_handler: EnemyHandler
// projectle_handler: ProjectleHandler

pub fn init(alloc: Allocator, server: *Server) Node {
    return .{
        .grid = .init(),
        .clients = .empty,
        .server = server,
        .alloc = alloc,
    };
}

pub fn deinit(self: *Node) void {
    self.grid.deinit(self.alloc);
    self.clients.deinit(self.alloc);
}

pub fn notifyAll(self: *Node, sender_id: usize, msg: *const proto.ServerResponse) !void {
    var it = self.clients.valueIterator();
    const buf = try buildServerResponsePayload(self.alloc, msg);
    defer self.alloc.free(buf);

    while (it.next()) |cli| {
        if (cli.*.client_id == sender_id)
            continue;
        cli.*.enqueueOutbound(.tcp, buf) catch {};
        self.server.kickClientWriter(cli.*.slot) catch {};
    }
}
