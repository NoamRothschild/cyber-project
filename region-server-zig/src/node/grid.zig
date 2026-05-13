const std = @import("std");
const Allocator = std.mem.Allocator;
const testing = std.testing;
const client = @import("../client.zig");
const Node = @import("node.zig");
const Grid = @This();

/// an object that can exist on the grid
pub const Object = union(enum) {
    dummy: struct { some_field: u32 },
};

// NOTE: optimization: replace with std.DynamicBitSetUnmanaged for a lower constant on lookup.
// set with .initFull(bit_length = player_count * threshold)
pub fn AutoSet(comptime T: type) type {
    return std.AutoHashMapUnmanaged(T, void);
}

pub fn Set(comptime T: type, comptime Context: type) type {
    return std.HashMapUnmanaged(T, void, Context, std.hash_map.default_max_load_percentage);
}

pub const CellField = struct {
    seen: AutoSet(client.ClientId),
    ever_seen: AutoSet(client.ClientId),
    obj: Object,
    uid: usize,
};

/// will allow us to look up objects on the grid by object, ignoring their `seen` list
pub const GridCellContext = struct {
    pub fn hash(self: @This(), key: CellField) u64 {
        _ = self;
        var hasher = std.hash.Wyhash.init(0);
        std.hash.autoHash(&hasher, key.uid);
        return hasher.final();
    }

    pub fn eql(self: @This(), a: CellField, b: CellField) bool {
        _ = self;
        return a.uid == b.uid;
    }
};

pub const cell_size = 200;

pub const grid_width = @divFloor(Node.width, cell_size);
pub const grid_height = @divFloor(Node.height, cell_size);

grid: [grid_width * grid_height]Set(CellField, GridCellContext),
next_free_uid: std.atomic.Value(usize),

pub fn init() Grid {
    var self: Grid = .{ .grid = undefined, .next_free_uid = .init(0) };
    for (&self.grid) |*cell|
        cell.* = .empty;

    return self;
}

pub fn deinit(self: *Grid, alloc: Allocator) void {
    for (&self.grid) |*cell| {
        var it = cell.keyIterator();
        while (it.next()) |v| {
            v.seen.deinit(alloc);
            v.ever_seen.deinit(alloc);
        }
        cell.deinit(alloc);
    }
}

pub inline fn to_grid_index(self: *const Grid, cell_x: usize, cell_y: usize) usize {
    _ = self;
    std.debug.assert(cell_x < grid_width);
    std.debug.assert(cell_y < grid_height);
    return cell_y * grid_width + cell_x;
}

/// adds an object to the grid and returns that said objects uid
pub fn add(self: *Grid, allocator: Allocator, obj: Object, cell_x: usize, cell_y: usize, seen: ?AutoSet(client.ClientId), ever_seen: ?AutoSet(client.ClientId), existing_uid: ?usize) Allocator.Error!usize {
    const uid = if (existing_uid) |u| u else self.next_free_uid.fetchAdd(1, .monotonic);
    const field: CellField = .{
        .obj = obj,
        .seen = if (seen) |s| s else .empty,
        .ever_seen = if (ever_seen) |s| s else .empty,
        .uid = uid,
    };
    try self.grid[self.to_grid_index(cell_x, cell_y)].put(allocator, field, {});
    return uid;
}

pub fn remove(self: *Grid, uid: usize, cell_x: usize, cell_y: usize) error{NotFound}!void {
    if (!self.grid[self.to_grid_index(cell_x, cell_y)].remove(.{ .uid = uid, .obj = undefined, .seen = undefined, .ever_seen = undefined }))
        return error.NotFound;
}

pub fn move(self: *Grid, allocator: Allocator, uid: usize, old_cx: usize, old_cy: usize, new_cx: usize, new_cy: usize) error{ NotFound, CouldntAddBackObjectOutOfMemory }!void {
    if ((old_cx == new_cx) and (old_cy == new_cy))
        return;

    if (self.grid[self.to_grid_index(old_cx, old_cy)].fetchRemove(.{ .uid = uid, .obj = undefined, .seen = undefined, .ever_seen = undefined })) |v| {
        const field = v.key;
        _ = self.add(allocator, field.obj, new_cx, new_cy, null, field.ever_seen, uid) catch |err| switch (err) {
            error.OutOfMemory => return error.CouldntAddBackObjectOutOfMemory,
        };
    } else return error.NotFound;
}

/// iterates over all cells a client sitting at (x, y) might be able to see
const CellIterator = struct {
    grid: *Grid,
    curr_x: usize = 0,
    curr_y: usize = 0,
    start_x: usize = 0,
    end_x: usize = 0,
    end_y: usize = 0,

    // TODO: take actual player pos instead of topleft
    // x0 = self.x_range[0]
    // y0 = self.y_range[0]
    // cs = RegionNode.CELL_SIZE
    // w = RegionNode._grid_w
    // cell_x_min = max(0, (pos[0] - self._VIEW_HALF_W - x0) // cs)
    // cell_x_max = min(w - 1, (pos[0] + self._VIEW_HALF_W - 1 - x0) // cs)
    // cell_y_min = max(0, (pos[1] - self._VIEW_HALF_H - y0) // cs)
    // cell_y_max = min(RegionNode._grid_h - 1, (pos[1] + self._VIEW_HALF_H - 1 - y0) // cs)

    pub fn init(grid: *Grid, topleft_x: usize, topleft_y: usize) CellIterator {
        return .{
            .grid = grid,
            .curr_x = topleft_x,
            .curr_y = topleft_y,
            .start_x = topleft_x,
            .end_x = @min(topleft_x + client.view_width_cells, grid_width - 1),
            .end_y = @min(topleft_y + client.view_height_cells, grid_height - 1),
        };
    }

    pub fn next(self: *CellIterator) ?*Set(CellField, GridCellContext) {
        if (self.curr_x > self.end_x) {
            self.curr_x = self.start_x;
            self.curr_y += 1;
        }
        if (self.curr_y > self.end_y)
            return null;

        defer self.curr_x += 1;
        return &self.grid.grid[self.grid.to_grid_index(self.curr_x, self.curr_y)];
    }
};

/// iterates over all objects a client sitting at (x, y) might be able to see
pub const ViewIterator = struct {
    cell_it: CellIterator,
    field_it: ?Set(CellField, GridCellContext).Iterator,

    pub fn init(grid: *Grid, topleft_x: usize, topleft_y: usize) ViewIterator {
        return .{
            .cell_it = .init(grid, topleft_x, topleft_y),
            .field_it = null,
        };
    }

    pub fn next(self: *ViewIterator) ?*CellField {
        while (true) {
            if (self.field_it == null) {
                if (self.cell_it.next()) |cell| {
                    self.field_it = cell.iterator();
                } else return null;
            }
            if (self.field_it.?.next()) |v| return v.key_ptr;
            self.field_it = null;
        }
    }
};

// TODO: write more unit tests
// also test Grid.move and ensure uid stays the same and no ghosts exist

test Grid {
    var grid = Grid.init();
    defer grid.deinit(testing.allocator);
    const uid = try grid.add(testing.allocator, .{ .dummy = .{ .some_field = 5 } }, 1, 1, null, null, null);

    var it = ViewIterator.init(&grid, 0, 0);
    try testing.expect(it.next().?.obj == .dummy);
    try testing.expect(it.next() == null);
    try testing.expect(uid == 0);
}

test move {
    var grid = Grid.init();
    defer grid.deinit(testing.allocator);
    const uid = try grid.add(testing.allocator, .{ .dummy = .{ .some_field = 5 } }, 1, 1, null, null, null);

    try grid.move(testing.allocator, uid, 1, 1, 5, 5);
    try testing.expect(grid.grid[grid.to_grid_index(1, 1)].size == 0);
    try testing.expect(grid.grid[grid.to_grid_index(5, 5)].size == 1);
}

test "grid iterator edges" {
    var grid = Grid.init();
    defer grid.deinit(testing.allocator);
    const uid = try grid.add(testing.allocator, .{ .dummy = .{ .some_field = 5 } }, grid_width - 1, grid_height - 1, null, null, null);

    var it = ViewIterator.init(&grid, grid_width - 1, grid_height - 1);
    try testing.expect(it.next().?.obj == .dummy);
    try testing.expect(it.next() == null);
    try testing.expect(uid == 0);
}
