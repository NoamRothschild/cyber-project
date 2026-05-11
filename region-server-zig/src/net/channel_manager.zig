const std = @import("std");
const Channel = @import("channel.zig");

pub fn ChannelManager(comptime capacity: comptime_int) type {
    return struct {
        const Self = @This();
        channels: [capacity]Channel = undefined,
        free_channels: std.bit_set.ArrayBitSet(usize, capacity) = .full,

        pub fn init() Self {
            var self: Self = .{};
            for (&self.channels) |*channel| channel.* = .{};
            return self;
        }

        pub fn takeChannel(self: *Self) !*Channel {
            if (self.free_channels.findFirstSet()) |idx| {
                self.free_channels.unset(idx);
                return &self.channels[idx];
            } else {
                return error.AllChannelsFull;
            }
        }

        pub fn returnChannel(self: *Self, channel: *Channel) void {
            self.free_channels.set(channelIndex(self, channel));
        }

        pub fn channelIndex(self: *const Self, channel: *const Channel) usize {
            const start_ptr = &self.channels[0];
            return (@intFromPtr(channel) - @intFromPtr(start_ptr)) / @sizeOf(Channel);
        }

        pub fn get(self: *Self, index: usize) *Channel {
            return &self.channels[index];
        }
    };
}
