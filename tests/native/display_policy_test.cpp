#include "../../firmware/custom_components/gym_native/display_policy.h"
#include <cassert>
#include <iostream>
#include <limits>
using esphome::gym_native::DisplayPolicy;
int main() {
  DisplayPolicy p;
  assert(!p.sleep(true, 22*60+59, 0));
  assert(p.sleep(true, 23*60, 0));
  assert(p.sleep(true, 0, 0));
  assert(p.sleep(true, 6*60+59, 0));
  assert(!p.sleep(true, 7*60, 0));
  p.wake(1000);
  assert(!p.sleep(true, 0, 300999));
  assert(p.sleep(true, 0, 301000));
  assert(!p.sleep(true, 7*60, 301000));
  const auto near_wrap = std::numeric_limits<uint32_t>::max()-1000;
  p.wake(near_wrap);
  assert(!p.sleep(true, 0, static_cast<uint32_t>(near_wrap+299999)));
  assert(p.sleep(true, 0, static_cast<uint32_t>(near_wrap+300000)));
  p.manual_sleep=true;
  assert(p.sleep(true, 12*60, 0));
  p.wake(0);
  assert(!p.sleep(true, 12*60, 0));
  p.enabled=false;
  assert(!p.sleep(false, 0, 400000));
  p.enabled=true;
  assert(p.sleep(false, 0, 400000));
  p.wake(400000);
  assert(!p.sleep(false, 0, 400001));
  p = DisplayPolicy{};
  p.start=9*60;p.end=17*60;p.touched=false;
  assert(!p.sleep(true, 8*60+59, 0));
  assert(p.sleep(true, 9*60, 0));
  assert(!p.sleep(true, 17*60, 0));
  p.end=p.start;
  assert(!p.night(true, 9*60));
  DisplayPolicy idle;
  assert(!idle.sleep(true, 12*60, 1799999));
  assert(idle.sleep(true, 12*60, 1800000));
  assert(idle.idle_seconds(1800000) == 1800);
  assert(idle.sleep(true, 7*60, 0));  // Expiry stays latched across counter wrap.
  idle.wake(1800001);
  assert(!idle.sleep(true, 12*60, 1800001));
  assert(!idle.idle_expired && idle.idle_seconds(1800001) == 0);
  idle.wake(3599000);
  assert(!idle.sleep(true, 12*60, 5398999));
  assert(idle.sleep(true, 12*60, 5399000));
  idle.wake(near_wrap);
  assert(!idle.sleep(true, 12*60, static_cast<uint32_t>(near_wrap+1799999)));
  assert(idle.sleep(true, 12*60, static_cast<uint32_t>(near_wrap+1800000)));
  idle = DisplayPolicy{};
  idle.enabled = false;  // Night schedule disabled, but idle off still applies.
  assert(!idle.sleep(false, 0, 1799999));
  assert(idle.sleep(false, 0, 1800000));
  idle.wake(1800000);
  idle.enabled = true;
  assert(!idle.sleep(true, 0, 2099999));
  assert(idle.sleep(true, 0, 2100000));  // Five-minute night wake is unchanged.
  std::cout<<"PASS: night, 30-minute idle boundary, touch renewal, wrap latch and clock loss\n";
}
