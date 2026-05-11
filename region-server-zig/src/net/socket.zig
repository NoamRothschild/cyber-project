const std = @import("std");
const Io = std.Io;
const net = Io.net;
const ConnectionType = @import("../client.zig").ConnectionType;

pub fn socket(io: Io, port: u16, comptime ip_ver: enum { ipv4, ipv6 }, comptime conn_t: ConnectionType, backlog: ?u31) !(if (conn_t == .tcp) net.Server else net.Socket) {
    const addr = try switch (ip_ver) {
        .ipv4 => net.IpAddress.parseIp4("127.0.0.1", port),
        .ipv6 => net.IpAddress.parseIp6("::1", port),
    };

    const default_kernel_backlog = 128;
    return switch (conn_t) {
        .tcp => addr.listen(io, .{ .kernel_backlog = backlog orelse default_kernel_backlog, .reuse_address = true }),
        .udp => addr.bind(io, .{ .mode = .dgram }),
    };
}
