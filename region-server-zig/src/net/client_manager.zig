const std = @import("std");
const linux = std.os.linux;
const Client = @import("../client.zig").Client;

pub const ClientSlot = struct {
    client: ?Client = null,
    in_flight: bool = false,
    tcp_channel_idx: ?usize = null,
    udp_peer_known: bool = false,
    udp_peer_addr: linux.sockaddr.storage = std.mem.zeroes(linux.sockaddr.storage),
    udp_peer_len: linux.socklen_t = @sizeOf(linux.sockaddr.storage),

    /// returns if the given slot is free or not
    pub fn slotFree(self: ClientSlot) bool {
        // TODO: will need to find a better way for setting && checking if slot is free
        // if I will multi-thread, a possibility that two threads take ownership of the same slot can happen since
        // setting self.client to not be null is decoupled from takeClientSlot.
        // Won't occur if we have only 1 thread allocating clients.
        return self.client == null;
    }
};

pub fn ClientContainer(comptime capacity: comptime_int) type {
    return struct {
        const Self = @This();
        raw: [capacity]ClientSlot = [_]ClientSlot{.{}} ** capacity,

        pub const init: Self = .{};

        pub inline fn at(self: *Self, index: usize) *ClientSlot {
            return &self.raw[index];
        }

        pub fn takeClientSlot(self: *Self) !usize {
            for (self.raw, 0..) |slot_state, i| {
                if (slot_state.client == null) return i;
            }
            return error.ClientsFull;
        }

        pub fn returnClientSlot(self: *Self, index: usize) void {
            self.raw[index] = .{};
        }

        pub fn findClientByUserId(self: *Self, user_id: usize) ?usize {
            for (self.raw, 0..) |slot_state, i| {
                if (slot_state.client) |c| {
                    if (c.client_id == user_id) return i;
                }
            }
            return null;
        }

        pub fn findClientByUdpPeer(self: *const Self, peer_addr: *const linux.sockaddr.storage, peer_len: linux.socklen_t) ?usize {
            for (self.raw, 0..) |slot_state, i| {
                if (!slot_state.udp_peer_known) continue;
                if (udpPeerEq(&slot_state.udp_peer_addr, slot_state.udp_peer_len, peer_addr, peer_len)) return i;
            }
            return null;
        }
    };
}

fn udpPeerEq(a_addr: *const linux.sockaddr.storage, a_len: linux.socklen_t, b_addr: *const linux.sockaddr.storage, b_len: linux.socklen_t) bool {
    if (a_len != b_len) return false;
    if (a_addr.family != b_addr.family) return false;
    const len: usize = @intCast(a_len);
    const a_bytes = std.mem.asBytes(a_addr);
    const b_bytes = std.mem.asBytes(b_addr);
    return std.mem.eql(u8, a_bytes[0..len], b_bytes[0..len]);
}
