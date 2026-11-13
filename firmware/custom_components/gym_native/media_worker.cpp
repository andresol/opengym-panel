#include "gym_native.h"

namespace esphome::gym_native {
bool GymNative::media_wanted(uint32_t context, const std::string &route) {
  if (context != context_.load() || media_paused_.load()) return false;
  lock_request();
  const bool wanted = wanted_command_.empty() &&
      (route == wanted_media_ || route == wanted_prefetch_);
  unlock_request();
  return wanted;
}

void GymNative::media_worker() {
  uint32_t seen_context = 0, seen_media = 0, attempted_at = 0;
  std::string attempted_route;
  for (;;) {
    const uint32_t context = context_.load();
    std::string route, prefetch;
    uint32_t media;
    lock_request();
    media = media_generation_.load(); route = wanted_media_; prefetch = wanted_prefetch_;
    const bool busy = pending_media_ready_ || !wanted_command_.empty();
    unlock_request();
    if (context != seen_context) { seen_context = context; seen_media = 0; attempted_route.clear(); }
    if (!busy && !media_paused_.load() && wifi::global_wifi_component->is_connected()) {
      const bool foreground = media != seen_media && !route.empty();
      if (!foreground) route = prefetch;
      // One current-exercise lookahead, never all profiles/routines. Failures
      // back off; navigation/commands can cancel obsolete body reads.
      if (!route.empty() && (foreground || route != attempted_route || millis() - attempted_at >= 30000)) {
        SharedMedia binary = cache_.find(route);
        bool ok = bool(binary);
        if (ok && foreground) ++cache_hits_;
        if (!ok) {
          if (route.compare(0, 11, "/packed-hq/") == 0) {
            cache_.discard_unused();
            cache_bytes_ = cache_.bytes();
          }
          if (foreground) ++media_downloads_; else ++prefetch_downloads_;
          auto download = std::make_shared<MediaBuffer>();
          std::string body;
          ok = get(route, body, MediaBuffer::MAX_BYTES, context, media, download.get());
          last_wire_bytes_ = ok ? download->size() : 0;
          ok = ok && unpack_media(*download);
          if (ok) { binary = std::move(download); cache_.put(route, binary); cache_bytes_ = cache_.bytes(); }
        }
        lock_request();
        if (context == context_.load()) {
          if (route == wanted_prefetch_) prefetch_ready_ = ok;
          // A tap during prefetch adopts the in-flight result, not a duplicate.
          if (route == wanted_media_ && !pending_media_ready_) {
            pending_binary_ = std::move(binary); pending_media_route_ = route;
            pending_media_context_ = context; pending_media_generation_ = media_generation_.load();
            pending_media_ready_ = true; seen_media = pending_media_generation_;
          }
          if (wanted_command_.empty() && (route == wanted_media_ || route == wanted_prefetch_)) {
            attempted_route = route; attempted_at = millis();
          }
        }
        unlock_request();
      }
    }
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

}  // namespace esphome::gym_native
