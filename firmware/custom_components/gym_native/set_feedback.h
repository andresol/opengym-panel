#pragma once
#include <algorithm>
#include <cstdint>
#include <string>
#include <utility>

namespace esphome::gym_native {

// A local command may only affect the view/timer after authoritative readback.
// The pending receipt also survives a lost reply until the next fresh poll.
struct SetFeedback {
  struct Effect { bool follow = false, rest = false; };
  bool pending = false, requested_done = false, was_complete = false;
  std::string session;
  unsigned revision = 0;
  int exercise = -1, row = -1, side = 0;
  uint32_t submitted_at = 0;

  void arm(const std::string &id, unsigned rev, int ex, int set, int set_side,
           bool done, bool complete, uint32_t now) {
    pending = true; session = id; revision = rev; exercise = ex; row = set;
    side = set_side; requested_done = done; was_complete = complete; submitted_at = now;
  }
  void cancel() { pending = false; }
  Effect observe(const std::string &id, unsigned rev, int selected, bool active,
                 bool target_done, bool complete, uint32_t now) {
    if (!pending) return {};
    if (session != id || exercise != selected || !active || now - submitted_at > 60000u) {
      cancel(); return {};
    }
    if (rev <= revision) return {};  // Old polling data is not an acknowledgement.
    cancel();
    const bool confirmed = requested_done && target_done;
    return {confirmed, confirmed && !was_complete && complete};
  }
};

// 54 px rows / 8 px gaps. Keep the last changed row (or both sides), a previous
// result and the next row in view where possible, clamped to real content bounds.
inline int follow_set_scroll(int last_row, int count, int viewport) {
  const int maximum = std::max(0, (count - 1) * 62 + 54 - viewport);
  return std::min(maximum, std::max(0, last_row * 62 - 62));
}

// Follow authoritative results on entry/resume, not just a local POST receipt.
// Unchanged background reads must leave the user's manual scroll alone.
struct SetScroll {
  std::string session, results;
  int exercise = -1;

  void reset() {
    session.clear();
    results.clear();
    exercise = -1;
  }

  template<typename Sets>
  int observe(const std::string &id, int selected, const Sets &sets,
              int viewport, int previous) {
    if (id.empty()) {
      reset();
      return previous;
    }
    std::string next;
    int first_pending = -1, last_done = -1;
    const auto append = [&](bool done) {
      const int row = static_cast<int>(next.size());
      next += done ? '1' : '0';
      if (done) last_done = row;
      else if (first_pending < 0) first_pending = row;
    };
    for (const auto &set : sets) {
      if (set.per_side) {
        append(set.left.done);
        append(set.right.done);
      } else append(set.value.done);
    }
    const bool changed = session != id || exercise != selected || results != next;
    session = id;
    exercise = selected;
    results = std::move(next);
    if (!changed) return previous;
    // Keep the last completed result beside the next set. For a fully completed
    // exercise, show the final results instead of returning to the first rows.
    const int anchor = first_pending >= 0 ? first_pending : last_done;
    return follow_set_scroll(anchor, static_cast<int>(results.size()), viewport);
  }
};
}  // namespace esphome::gym_native
