#include "../../firmware/custom_components/gym_native/set_feedback.h"
#include "../../firmware/custom_components/gym_native/timer.h"
#include <cassert>
#include <iostream>
#include <vector>
using esphome::gym_native::SetFeedback;
using esphome::gym_native::follow_set_scroll;
using esphome::gym_native::SetScroll;
using esphome::gym_panel::Timer;

int main() {
  SetFeedback feedback;
  const auto arm = [&](bool was_complete = false, bool done = true, int side = 0) {
    feedback.arm("session-a", 7, 2, 4, side, done, was_complete, 1000);
  };
  const auto observe = [&](bool target, bool pair, unsigned revision = 8) {
    return feedback.observe("session-a", revision, 2, true, target, pair, 2000);
  };
  arm();
  auto effect = observe(false, false, 7);
  assert(!effect.follow && !effect.rest && feedback.pending); // No optimistic timer.
  effect = observe(true, true);
  assert(effect.follow && effect.rest && !feedback.pending);
  effect = observe(true, true);
  assert(!effect.follow && !effect.rest); // No restart on duplicated ack/poll.

  for (int first_side : {1, 2}) {
    arm(false, true, first_side);
    effect = observe(true, false);
    assert(effect.follow && !effect.rest); // Either side can be recorded first.
    arm(false, true, 3 - first_side);
    effect = observe(true, true);
    assert(effect.follow && effect.rest); // Exactly one rest per completed pair.
  }
  arm(true); effect = observe(true, true);
  assert(effect.follow && !effect.rest); // Editing an already-done set/pair.
  arm(true, false); effect = observe(false, false);
  assert(!effect.follow && !effect.rest); // Undo is not completion.
  arm(); feedback.cancel(); effect = observe(true, true);
  assert(!effect.rest && !effect.follow); // Explicit error response.
  arm(); effect = observe(false, false);
  assert(!effect.rest && !effect.follow); // New revision did not confirm done.
  arm(); // Lost reply followed by fresh authoritative polling data.
  assert(!observe(false, false, 7).rest);
  effect = observe(true, true);
  assert(effect.rest && effect.follow);

  arm(); effect = feedback.observe("session-b", 8, 2, true, true, true, 2000);
  assert(!effect.rest && !feedback.pending);
  arm(); effect = feedback.observe("session-a", 8, 3, true, true, true, 2000);
  assert(!effect.rest && !feedback.pending);
  arm(); effect = feedback.observe("session-a", 8, 2, false, true, true, 2000);
  assert(!effect.rest && !feedback.pending);
  arm(); effect = feedback.observe("session-a", 8, 2, true, true, true, 61001);
  assert(!effect.rest && !feedback.pending); // No delayed surprise after timeout.
  feedback.arm("session-a", 7, 2, 4, 0, true, false, 0xfffffff0u);
  effect = feedback.observe("session-a", 8, 2, true, true, true, 0x00000010u);
  assert(effect.rest); // millis rollover.

  Timer timer;
  timer.reset(180); timer.toggle(1000, 180);
  assert(timer.running && timer.remaining(2000) == 179);
  timer.reset(0); timer.toggle(1000, 0);
  assert(!timer.running); // A prescribed zero rest remains zero.

  assert(follow_set_scroll(0, 10, 194) == 0);
  assert(follow_set_scroll(4, 10, 194) == 186);
  assert(follow_set_scroll(5, 10, 194) == 248); // Both sides 4/5 stay visible.
  assert(4 * 62 >= 248 && 5 * 62 + 54 <= 248 + 194);
  assert(follow_set_scroll(9, 10, 194) == 418); // Last row wholly visible.
  assert(9 * 62 + 54 == 418 + 194);
  assert(follow_set_scroll(1, 2, 194) == 0); // Short lists never overscroll.

  struct Result { bool done = false; };
  struct Set { Result value, left, right; bool per_side = false; };
  std::vector<Set> rows(5);
  SetScroll scroll;
  for (auto &row : rows) row.value.done = true;
  assert(scroll.observe("session-a", 0, rows, 194, 0) == 108); // Reopen completed results.
  assert(scroll.observe("session-a", 0, rows, 194, 17) == 17); // Poll preserves manual review.
  scroll.reset();
  assert(scroll.observe("session-a", 0, rows, 194, 0) == 108); // Reselect same exercise.
  rows[2].value.done = false;
  assert(scroll.observe("session-a", 0, rows, 194, 108) == 62); // Undo reveals pending row.
  rows[2].value.done = true;
  assert(scroll.observe("session-a", 0, rows, 194, 0) == 108); // Remote completion follows too.
  assert(scroll.observe("session-b", 0, rows, 240, 0) == 62); // New session, compact viewport.
  assert(scroll.observe("", 0, rows, 194, 21) == 21); // No workout, no automatic jump.
  for (auto &row : rows) { row.per_side = true; row.left.done = row.right.done = true; }
  rows[4].left.done = false;
  assert(scroll.observe("session-b", 2, rows, 240, 0) == 372); // Left pending, right already done.
  rows[4].left.done = true;
  assert(scroll.observe("session-b", 2, rows, 240, 0) == 372); // Final pair fully visible.
  assert(scroll.observe("session-b", 2, rows, 240, 100) == 100);
  rows.clear();
  assert(scroll.observe("session-b", 2, rows, 240, 100) == 0); // Empty content is bounded.
  std::cout << "Set feedback: confirmed completion, both side orders, edits/undo/errors, readback, identity, timeout, zero rest and scroll bounds passed\n";
}
