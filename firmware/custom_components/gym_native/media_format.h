#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace esphome::gym_native {

// Validate before keeping an immutable public catalogue image in the cache.
// Requested still/animation mode is checked separately when binding to LVGL.
inline bool valid_media(const uint8_t *data, size_t size) {
  if (!data || size < 12 || std::memcmp(data, "GYM1", 4) != 0) return false;
  auto word = [&](unsigned offset) {
    return unsigned(data[offset]) | (unsigned(data[offset + 1]) << 8);
  };
  const unsigned width = word(4), height = word(6), frames = word(8), delay = word(10);
  const bool still = width == 512 && height == 360 && frames == 1 && delay == 0;
  const bool animation = width == 320 && height == 224 && frames >= 1 && frames <= 24 &&
                         delay >= 100 && delay <= 20000;
  return (still || animation) && size == 12 + size_t(width) * height * frames * 2;
}
}  // namespace esphome::gym_native
