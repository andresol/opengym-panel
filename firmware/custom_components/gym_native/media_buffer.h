#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <memory>

#ifdef USE_ESP32
#include "esp_heap_caps.h"
#endif

namespace esphome::gym_native {

// Own large media explicitly in PSRAM. std::string/new use internal memory on
// this ESPHome build and abort when a multi-megabyte allocation cannot fit.
// Keep the 12-byte transport header immediately before 64-byte-aligned pixels.
class MediaBuffer {
 public:
  using Allocate = void *(*)(size_t);
  static constexpr size_t MAX_BYTES = 12 + size_t(512) * 360 * 24 * 2;
  static constexpr size_t PREFIX = 64 - 12;

  bool allocate(size_t bytes, Allocate allocator = default_allocate) {
    if (bytes < 12 || bytes > MAX_BYTES) return false;
    const size_t allocation = (bytes + PREFIX + 63) & ~size_t(63);
    auto *pointer = static_cast<uint8_t *>(allocator(allocation));
    if (!pointer) return false;  // Ordinary recoverable media failure, not panic.
    storage_.reset(pointer);
    length_ = bytes;
    return true;
  }

  uint8_t *data() const { return storage_ ? storage_.get() + PREFIX : nullptr; }
  size_t size() const { return storage_ ? length_ : 0; }
  void reset() { storage_.reset(); length_ = 0; }

 protected:
  static void *default_allocate(size_t bytes) {
#ifdef USE_ESP32
    return heap_caps_aligned_alloc(64, bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
#else
    return std::aligned_alloc(64, bytes);
#endif
  }
  struct Free {
    void operator()(uint8_t *pointer) const { std::free(pointer); }
  };
  std::unique_ptr<uint8_t, Free> storage_;
  size_t length_ = 0;
};
}  // namespace esphome::gym_native
