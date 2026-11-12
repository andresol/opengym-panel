"""Run production exercise navigation against the real timer and feedback model.

No panel/network/workout data is used. Navigation must not change a running
countdown's absolute deadline, even across different rest prescriptions.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'firmware/custom_components/gym_native'


class RestNavigationTests(unittest.TestCase):
    def test_navigation_preserves_running_rest(self):
        cpp = (COMPONENT / 'gym_native.cpp').read_text()
        method = cpp.split('void GymNative::choose_exercise(', 1)[1]
        method = 'void GymNative::choose_exercise(' + method.split('void GymNative::request_media(', 1)[0]
        source = r'''
#include "timer.h"
#include "set_feedback.h"
#include <cassert>
#include <cstdint>
#include <vector>

uint32_t now = 1000;
uint32_t millis() { return now; }
constexpr int LV_ANIM_OFF = 0;
void lv_obj_scroll_to_y(int, int, int) {}
void lv_obj_scroll_to_view(int, int) {}

class GymNative {
 public:
  struct Exercise { uint32_t rest; };
  bool valid_ = true, playing_ = true;
  int selected_ = 0, rows_ = 1, renders = 0, requests = 0;
  std::vector<Exercise> exercises_ = {{180}, {90}, {0}};
  std::vector<int> exercise_buttons_ = {10, 11, 12};
  esphome::gym_panel::Timer timer_;
  esphome::gym_native::SetFeedback set_feedback_;
  esphome::gym_native::SetScroll set_scroll_;
  void choose_exercise(int index);
  void render_exercise() { ++renders; }
  void request_media() { ++requests; }
};
'''
        tests = r'''
int main() {
  GymNative screen;
  auto &timer = screen.timer_;
  timer.reset(180);
  timer.toggle(now, 180);
  now += 125000;
  const uint32_t original_deadline = timer.deadline;
  assert(timer.running && timer.remaining(now) == 55);
  screen.set_feedback_.arm("synthetic", 1, 0, 0, 0, true, false, now);

  screen.choose_exercise(screen.selected_ + 1);  // Next, 180s -> 90s preset.
  assert(screen.selected_ == 1 && !screen.playing_);
  assert(timer.running && timer.deadline == original_deadline);
  assert(timer.remaining(now) == 55 && !screen.set_feedback_.pending);
  now += 1000;
  screen.choose_exercise(2);                    // List selection, zero preset.
  assert(timer.running && timer.deadline == original_deadline);
  assert(timer.remaining(now) == 54);
  screen.choose_exercise(screen.selected_ - 1); // Previous.
  screen.choose_exercise(0);                    // Jump back to the original.
  screen.choose_exercise(0);                    // Same exercise selected again.
  assert(timer.running && timer.deadline == original_deadline);
  assert(timer.remaining(now) == 54 && screen.renders == 5 && screen.requests == 5);

  timer.adjust(15, now);                        // A user extension is retained.
  const uint32_t extended_deadline = timer.deadline;
  now += 1000;
  screen.choose_exercise(1);
  assert(timer.running && timer.deadline == extended_deadline);
  assert(timer.remaining(now) == 68);

  // Rejected navigation must not alter the active exercise or timer.
  screen.choose_exercise(-1);
  screen.choose_exercise(3);
  screen.valid_ = false;
  screen.choose_exercise(0);
  assert(screen.selected_ == 1 && timer.deadline == extended_deadline && timer.running);
  screen.valid_ = true;

  // Before the periodic tick processes expiry, it is still an expired timer.
  now = timer.deadline;
  screen.choose_exercise(1);
  assert(!timer.running && timer.remaining(now) == 90);
  screen.choose_exercise(2);
  assert(!timer.running && timer.remaining(now) == 0);
  screen.choose_exercise(0);
  assert(!timer.running && timer.remaining(now) == 180);

  // Existing stopped/manual-stop behaviour: follow the newly selected preset.
  timer.toggle(now, 180);
  now += 1000;
  timer.toggle(now, 180);
  assert(!timer.running && timer.remaining(now) == 179);
  screen.choose_exercise(1);
  assert(!timer.running && timer.remaining(now) == 90);

  // Real millis() rollover must preserve the same deadline/countdown as well.
  now = 0xffff0000u;
  timer.reset(180);
  timer.toggle(now, 180);
  const uint32_t wrapped_deadline = timer.deadline;
  now = 0x00001000u;
  const uint32_t wrapped_remaining = timer.remaining(now);
  assert(wrapped_remaining > 0 && wrapped_remaining < 180);
  screen.choose_exercise(2);
  assert(timer.running && timer.deadline == wrapped_deadline);
  assert(timer.remaining(now) == wrapped_remaining);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(source + method + tests)
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(COMPONENT), str(path / 'test.cpp'),
                            '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True, timeout=10)
