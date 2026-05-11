const std = @import("std");
const Io = std.Io;
const Server = @import("server.zig").Server;

pub fn main(init: std.process.Init) !void {
    var svr: Server = try .init(init.gpa, init.io, 8826);
    defer svr.deinit(init.io);
    _ = try svr.run();

    std.mem.sort(usize, svr.fd_cnt[0..], {}, std.sort.desc(usize));
    for (0..15) |i| {
        std.debug.print("{d}, ", .{svr.fd_cnt[i]});
    }
}
