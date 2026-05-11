const std = @import("std");
const linux = std.os.linux;

const Channel = @This();
type: ChannelType,
sock_fd: posix.fd_t,
sock_type: SocketType,
buf: RecvBuffer,
_buf: [1024]u8,

const posix = std.posix;
const RecvBuffer = linux.IoUring.RecvBuffer;
pub const SocketType = enum(u1) { tcp, udp };
pub const ChannelType = enum(u8) {
    accept,
    read,
    write,
};
