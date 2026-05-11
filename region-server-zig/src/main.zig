const std = @import("std");
const Io = std.Io;
const Server = @import("server.zig").Server;

pub fn main(init: std.process.Init) !void {
    var svr: Server = try .init(init.gpa, init.io, 8826);
    defer svr.deinit(init.io);
    _ = try svr.run();
}
