#pragma once

#include "media_buffer.h"
#include <list>
#include <memory>
#include <string>

namespace esphome::gym_native {

using SharedMedia = std::shared_ptr<MediaBuffer>;

// The fetch worker alone owns the LRU. The UI holds a separate shared reference,
// so eviction cannot free pixels which LVGL is still drawing. Bulk data remains
// PSRAM-only; keys and small ownership records are ordinary bounded metadata.
class MediaCache {
 public:
  static constexpr size_t BYTE_LIMIT = 12 * 1024 * 1024;
  static constexpr size_t ENTRY_LIMIT = 48;

  explicit MediaCache(size_t limit = BYTE_LIMIT) : limit_(limit) {}

  SharedMedia find(const std::string &route) {
    for (auto it = entries_.begin(); it != entries_.end(); ++it) {
      if (it->route != route) continue;
      auto data = it->data;
      entries_.splice(entries_.begin(), entries_, it);
      return data;
    }
    return {};
  }

  void put(const std::string &route, const SharedMedia &data) {
    if (!data || !data->size() || data->size() > limit_) return;
    for (auto it = entries_.begin(); it != entries_.end(); ++it) {
      if (it->route == route) {
        bytes_ -= it->data->size();
        entries_.erase(it);
        break;
      }
    }
    while (!entries_.empty() &&
           (bytes_ + data->size() > limit_ || entries_.size() >= ENTRY_LIMIT)) {
      bytes_ -= entries_.back().data->size();
      entries_.pop_back();
    }
    entries_.push_front({route, data});
    bytes_ += data->size();
  }

  // Before a large HQ miss, release obsolete cache ownership. The displayed
  // image and pending handoff retain their independent shared references.
  void discard_unused() {
    for (auto it = entries_.begin(); it != entries_.end();) {
      if (it->data.use_count() == 1) {
        bytes_ -= it->data->size();
        it = entries_.erase(it);
      } else {
        ++it;
      }
    }
  }

  size_t bytes() const { return bytes_; }
  size_t size() const { return entries_.size(); }

 protected:
  struct Entry {
    std::string route;
    SharedMedia data;
  };
  std::list<Entry> entries_;
  size_t bytes_ = 0;
  size_t limit_;
};
}  // namespace esphome::gym_native
