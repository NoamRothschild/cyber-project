const std = @import("std");
const Allocator = std.mem.Allocator;

const Grid = @import("grid.zig");
const client = @import("../client.zig");
const Node = @This();

// NOTE: one node now holds the same space as all old nodes (the whole map)
pub const width = 4600 * 17;
pub const height = 2200 * 20;

grid: Grid,
clients: std.AutoHashMapUnmanaged(client.ClientId, client.Client),
alloc: Allocator,
// enemy_handler: EnemyHandler
// projectle_handler: ProjectleHandler

pub fn init(alloc: Allocator) Node {
    return .{
        .grid = .init(),
        .clients = .empty,
        .alloc = alloc,
    };
}

pub fn deinit(self: *Node) void {
    self.grid.deinit(self.alloc);
    self.clients.deinit(self.alloc);
}
