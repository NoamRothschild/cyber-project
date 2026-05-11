const std = @import("std");
const linux = std.os.linux;
const posix = std.posix;

pub const SocketType = enum(u1) { tcp, udp };
pub const ChannelType = enum(u8) {
    accept,
    tcp_read,
    tcp_write,
    udp_read,
    udp_write,
};

const Channel = @This();

pub const read_buf_size = 4096;
pub const write_buf_size = 4096;

type: ChannelType = .accept,
sock_type: SocketType = .tcp,
sock_fd: posix.fd_t = -1,
client_slot: ?usize = null,

read_buf: [read_buf_size]u8 = undefined,
read_used: usize = 0,

write_buf: [write_buf_size]u8 = undefined,
write_len: usize = 0,
write_off: usize = 0,
write_client_slot: ?usize = null,

udp_peer_addr: linux.sockaddr.storage = std.mem.zeroes(linux.sockaddr.storage),
udp_peer_addr_len: linux.socklen_t = @sizeOf(linux.sockaddr.storage),
udp_iov: std.posix.iovec = undefined,
udp_recv_msghdr: linux.msghdr = undefined,
udp_send_iov: std.posix.iovec_const = undefined,
udp_send_msghdr: linux.msghdr_const = undefined,

pub fn resetForAccept(self: *Channel) void {
    self.* = .{};
    self.type = .accept;
    self.sock_type = .tcp;
}

pub fn resetForTcpRead(self: *Channel, fd: posix.fd_t, slot: ?usize) void {
    self.type = .tcp_read;
    self.sock_type = .tcp;
    self.sock_fd = fd;
    self.client_slot = slot;
    self.write_len = 0;
    self.write_off = 0;
    self.write_client_slot = null;
}

pub fn resetForUdpRead(self: *Channel, fd: posix.fd_t) void {
    self.type = .udp_read;
    self.sock_type = .udp;
    self.sock_fd = fd;
    self.client_slot = null;
    self.read_used = 0;
    self.write_len = 0;
    self.write_off = 0;
    self.write_client_slot = null;
    self.udp_peer_addr = std.mem.zeroes(linux.sockaddr.storage);
    self.udp_peer_addr_len = @sizeOf(linux.sockaddr.storage);
}

pub fn setupUdpRecvMsg(self: *Channel) void {
    const recv_slice = self.read_buf[0..];
    self.udp_iov = .{
        .base = recv_slice.ptr,
        .len = recv_slice.len,
    };
    self.udp_recv_msghdr = .{
        .name = @ptrCast(&self.udp_peer_addr),
        .namelen = self.udp_peer_addr_len,
        .iov = @ptrCast(&self.udp_iov),
        .iovlen = 1,
        .control = null,
        .controllen = 0,
        .flags = 0,
    };
}

pub fn setupUdpSendMsg(self: *Channel) void {
    const send_slice = self.write_buf[self.write_off..self.write_len];
    self.udp_send_iov = .{
        .base = send_slice.ptr,
        .len = send_slice.len,
    };
    self.udp_send_msghdr = .{
        .name = @ptrCast(&self.udp_peer_addr),
        .namelen = self.udp_peer_addr_len,
        .iov = @ptrCast(&self.udp_send_iov),
        .iovlen = 1,
        .control = null,
        .controllen = 0,
        .flags = 0,
    };
}
