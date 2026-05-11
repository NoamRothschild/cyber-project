const std = @import("std");
const Io = std.Io;
const net = Io.net;
const linux = std.os.linux;
const IoUring = linux.IoUring;

pub fn init_ring(ring_size: u16) !IoUring {
    var params = std.mem.zeroes(linux.io_uring_params);
    params.flags = linux.IORING_SETUP_SINGLE_ISSUER | linux.IORING_SETUP_CLAMP | linux.IORING_SETUP_CQSIZE | linux.IORING_SETUP_DEFER_TASKRUN;
    params.cq_entries = @as(u32, ring_size);

    return IoUring.init_params(ring_size, &params);
}
