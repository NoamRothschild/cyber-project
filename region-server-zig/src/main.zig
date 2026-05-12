const std = @import("std");
const Io = std.Io;
const Server = @import("net/server.zig").Server;
const Node = @import("node/node.zig");

pub fn main(init: std.process.Init) !void {
    const svr = try init.gpa.create(Server);
    defer init.gpa.destroy(svr);

    try svr.init(init.gpa, init.io, 8826);
    defer svr.deinit(init.io);

    std.debug.print("listening for new connections...\n", .{});
    _ = try svr.run(init.io);
}

test {
    std.testing.refAllDecls(@This());
    std.testing.refAllDecls(Node);
    std.testing.refAllDecls(@import("node/grid.zig"));
}
