const std = @import("std");

pub const max_payload_len: usize = 512;
pub const frame_header_len = 4;
pub const max_frame_len = frame_header_len + max_payload_len;

pub fn buildHandshakePayload(buf: []u8, suffix: []const u8) ![]const u8 {
    const needed = frame_header_len + suffix.len;
    if (needed > buf.len) return error.MessageTooLarge;
    @memset(buf[0..frame_header_len], 0);
    @memcpy(buf[frame_header_len .. frame_header_len + suffix.len], suffix);
    return buf[0..needed];
}

pub fn prepareFramedMessage(buf: []u8, payload: []const u8) !void {
    if (payload.len > max_payload_len) return error.MessageTooLarge;
    const total = frame_header_len + payload.len;
    if (total > buf.len) return error.MessageTooLarge;
    const len_buf: *[4]u8 = @ptrCast(buf[0..frame_header_len]);
    std.mem.writeInt(u32, len_buf, @intCast(payload.len), .little);
    @memcpy(buf[frame_header_len..total], payload);
}

/// takes a message and returns the size specified in its first 4 bytes.
pub fn length(msg: []const u8) error{MessageTooLarge}!usize {
    const len_buf: *const [4]u8 = @ptrCast(msg[0..frame_header_len]);
    const msg_len = std.mem.readInt(u32, len_buf, .little);
    if (msg_len > max_payload_len)
        return error.MessageTooLarge;
    return msg_len;
}
