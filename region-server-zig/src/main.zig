const std = @import("std");
const Io = std.Io;
const Server = @import("server.zig").Server;

pub fn main(init: std.process.Init) !void {
    const svr = try init.gpa.create(Server);
    defer init.gpa.destroy(svr);

    try svr.init(init.gpa, init.io, 8826);
    defer svr.deinit(init.io);

    _ = try svr.run();
}
