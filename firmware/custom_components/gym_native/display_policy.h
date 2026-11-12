#pragma once
#include <algorithm>
#include <cstdint>

namespace esphome::gym_native {
// All times are local minutes after midnight; the RTC owns timezone and DST.
struct DisplayPolicy {
  static constexpr uint32_t IDLE_TIMEOUT_MS = 30U * 60U * 1000U;
  bool enabled = true, touched = false, manual_sleep = false;
  bool idle_expired = false;
  int start = 23 * 60, end = 7 * 60, day_percent = 100, night_percent = 20;
  uint32_t wake_ms = 5 * 60 * 1000, last_touch = 0;

  bool night(bool valid_clock, int minute) const {
    if (!enabled) return false;
    if (!valid_clock) return true;  // Unknown time never lights the room at 100%.
    if (start == end) return false;
    return start < end ? minute >= start && minute < end : minute >= start || minute < end;
  }
  bool sleep(bool valid_clock, int minute, uint32_t now) {
    // Only interaction renews this lease, not polling, animation or a timer.
    // Latch expiry so millis() wrapping cannot wake an unused screen later.
    if (static_cast<uint32_t>(now - last_touch) >= IDLE_TIMEOUT_MS) idle_expired = true;
    return manual_sleep || idle_expired || (night(valid_clock, minute) &&
        (!touched || static_cast<uint32_t>(now - last_touch) >= wake_ms));
  }
  uint32_t idle_seconds(uint32_t now) const {
    return idle_expired ? IDLE_TIMEOUT_MS / 1000U :
        std::min(static_cast<uint32_t>(now - last_touch), IDLE_TIMEOUT_MS) / 1000U;
  }
  void wake(uint32_t now) {
    touched = true;
    manual_sleep = false;
    idle_expired = false;
    last_touch = now;
  }
};
}  // namespace esphome::gym_native
