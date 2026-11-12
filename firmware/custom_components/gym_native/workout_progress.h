#pragma once
#include <string>
#include "ui_text.h"
namespace esphome::gym_native {
struct WorkoutProgress {
  unsigned work_done = 0, work_total = 0, warmup_done = 0, warmup_total = 0;
  int next_row = -1, next_side = 0;
  unsigned next_ordinal = 0;
  bool next_warmup = false;
  bool complete() const { return next_row < 0 && work_total + warmup_total > 0; }
  std::string next_caption(const UiText &ui = {}) const {
    if (complete()) return ui.tr("Fullført", "Complete");
    if (next_row < 0) return {};
    return std::string(next_warmup ? ui.tr("Oppv. ", "Warm-up ") : ui.tr("Sett ", "Set ")) +
        std::to_string(next_ordinal) + ui.tr(" av ", " of ") +
        std::to_string(next_warmup ? warmup_total : work_total) +
        (next_side == 1 ? ui.tr(" · Venstre", " · Left") :
         next_side == 2 ? ui.tr(" · Høyre", " · Right") : "");
  }
};
// A unilateral set counts as complete only after BOTH sides. An undone earlier
// set becomes next again; no optimistic/local completion before server readback.
template<typename Sets> WorkoutProgress workout_progress(const Sets &sets) {
  WorkoutProgress p;
  for (size_t i = 0; i < sets.size(); ++i) {
    const auto &s = sets[i];
    const unsigned ordinal = s.warmup ? ++p.warmup_total : ++p.work_total;
    const bool done = s.per_side ? s.left.done && s.right.done : s.value.done;
    if (done) { if (s.warmup) ++p.warmup_done; else ++p.work_done; }
    else if (p.next_row < 0) {
      p.next_row = static_cast<int>(i); p.next_warmup = s.warmup;
      p.next_ordinal = ordinal; p.next_side = s.per_side ? (s.left.done ? 2 : 1) : 0;
    }
  }
  return p;
}

// Continue forwards, skipping finished/empty exercises. Wrap only when an earlier
// exercise still has an unfinished set (for example after manual navigation).
template<typename Exercises> int next_pending_exercise(const Exercises &exercises, int selected) {
  const int count = static_cast<int>(exercises.size());
  if (selected < 0 || selected >= count) return -1;
  for (int offset = 1; offset < count; ++offset) {
    const int index = (selected + offset) % count;
    if (workout_progress(exercises[index].sets).next_row >= 0) return index;
  }
  return -1;
}

template<typename Exercises> bool all_exercises_complete(const Exercises &exercises) {
  bool has_sets = false;
  for (const auto &exercise : exercises) {
    if (exercise.sets.empty()) continue;
    has_sets = true;
    if (!workout_progress(exercise.sets).complete()) return false;
  }
  return has_sets;
}
inline std::string decimal_text(std::string value) {
  for (size_t i = 1; i + 1 < value.size(); ++i)
    if (value[i] == '.' && value[i-1] >= '0' && value[i-1] <= '9' &&
        value[i+1] >= '0' && value[i+1] <= '9') value[i] = ',';
  return value;
}
}  // namespace esphome::gym_native
