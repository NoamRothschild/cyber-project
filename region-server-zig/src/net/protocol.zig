const std = @import("std");
const proto = @import("../proto/game/region.pb.zig");

pub const max_payload_len: usize = 512;
pub const frame_header_len = 4;
pub const max_frame_len = frame_header_len + max_payload_len;

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

/// Wrapper that generates a fn for [ProtobufMessageType].encode that doesn't take a writer. caller responsible for freeing the memory.
fn buildPayload(comptime T: type) fn (alloc: std.mem.Allocator, pkt: *const T) (std.Io.Writer.Error || std.mem.Allocator.Error)![]const u8 {
    return struct {
        pub fn build(alloc: std.mem.Allocator, pkt: *const T) (std.Io.Writer.Error || std.mem.Allocator.Error)![]const u8 {
            var aw = std.Io.Writer.Allocating.init(alloc);
            defer aw.deinit();
            try pkt.encode(&aw.writer, alloc);
            return aw.toOwnedSlice();
        }
    }.build;
}

/// Wrapper for HandshakeStart.encode that doesn't take a writer. caller responsible for freeing the memory.
pub const buildHandshakePayload = buildPayload(proto.HandshakeStart);

/// Wrapper for ServerResponse.encode that doesn't take a writer. caller responsible for freeing the memory.
pub const buildServerResponsePayload = buildPayload(proto.ServerResponse);
