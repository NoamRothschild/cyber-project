const Channel = @This();
type: ChannelType,
sock_fd: posix.fd_t,
buf: RecvBuffer,
_buf: [1024]u8,

const posix = @import("std").posix;
const RecvBuffer = @import("std").os.linux.IoUring.RecvBuffer;
pub const ChannelType = enum(u8) {
    accept,
    read,
    write,
};
