const std = @import("std");
const Io = std.Io;
const net = Io.net;
const linux = std.os.linux;
const IoUring = linux.IoUring;

pub fn createListeningSock(io: Io, port: u16, comptime ip_ver: enum { ipv4, ipv6 }, backlog: u31) !net.Server {
    comptime {
        if (ip_ver == .ipv6)
            @compileError("ipv6 not supported yet. TODO");
    }

    const addr = try net.IpAddress.parseIp4("127.0.0.1", port);
    return addr.listen(io, .{ .kernel_backlog = backlog, .reuse_address = true });
}

pub fn init_ring(ring_size: u16) !IoUring {
    var params = std.mem.zeroes(linux.io_uring_params);
    params.flags = linux.IORING_SETUP_SINGLE_ISSUER | linux.IORING_SETUP_CLAMP | linux.IORING_SETUP_CQSIZE | linux.IORING_SETUP_DEFER_TASKRUN;
    params.cq_entries = 1024;

    return IoUring.init_params(ring_size, &params);
}
