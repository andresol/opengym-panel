#include "../../firmware/custom_components/gym_native/weight_control.h"
#include <cassert>
#include "../../firmware/custom_components/gym_native/muscle_mask.h"
#include <limits>
#include <iostream>
using namespace esphome::gym_native;
int main() {
  const std::vector<float> weights{0, 5, 10, 17.5f, 25};
  assert(valid_stack_weights(weights));
  assert(!valid_stack_weights({0}));
  assert(!valid_stack_weights({0, 5, 5}));
  assert(!valid_stack_weights({0, std::numeric_limits<float>::infinity()}));
  for (size_t plate = 0; plate < weights.size(); ++plate) {
    assert(adjust_stack_weight(weights[plate], 1, weights) == weights[std::min(weights.size()-1, plate+1)]);
    assert(adjust_stack_weight(weights[plate], -1, weights) == weights[plate == 0 ? 0 : plate-1]);
  }
  assert(adjust_stack_weight(11, 1, weights) == 17.5f);
  assert(adjust_stack_weight(11, -1, weights) == 10);
  assert(adjust_stack_weight(7.25f, 1, {}) == 7.25f);
  WeightEntry keypad;
  keypad.reset(7.255f);
  assert(!keypad.edited && keypad.value() == 7.255f);
  assert(keypad.key('7') && keypad.key(',') && keypad.key('3'));
  assert(keypad.value() == 7.3f);
  assert(keypad.key('5') && !keypad.key('9') && keypad.value() == 7.35f);
  assert(!keypad.key(',') && keypad.value() == 7.35f);
  while (!keypad.text.empty()) assert(keypad.key(-1));
  assert(!keypad.valid());
  assert(keypad.key(',') && keypad.key('5') && keypad.value() == 0.5f);
  keypad.reset(1);
  for (char c : std::string("10000")) assert(keypad.key(c));
  assert(keypad.value() == 10000 && !keypad.key('1'));
  assert(keypad.key(',') && keypad.key('0') && !keypad.key('1'));
  assert(keypad.value() == 10000);
  keypad.reset(99);
  assert(keypad.key('0') && keypad.value() == 0 && keypad.valid());
  unsigned pixels = 0;
  for (const auto &run : MUSCLE_RUNS) { assert(run.count > 0 && run.part < 20); pixels += run.count; }
  assert(pixels == 384 * 320);

  assert((result_steps(0, "reps") == std::vector<int>{1,5,10,50}));
  assert((result_steps(1, "reps") == std::vector<int>{1,5,10}));
  assert((result_steps(1, "time") == std::vector<int>{1,3,6}));
  assert((result_steps(1, "cardio") == std::vector<int>{1,2,10}));
  assert((result_steps(2, "cardio") == std::vector<int>{1,5,10}));
  assert(std::fabs(adjust_weight(7.2f, 1) - 7.3f) < 0.00001f);
  assert(std::fabs(adjust_weight(7.3f, -1) - 7.2f) < 0.00001f);
  assert(std::fabs(adjust_weight(7.3f, 5) - 7.8f) < 0.00001f);
  assert(std::fabs(adjust_weight(7.8f, -5) - 7.3f) < 0.00001f);
  float light = 2.3f;
  for (int i = 0; i < 10000; ++i) light = adjust_weight(adjust_weight(light, 5), -5);
  assert(std::fabs(light - 2.3f) < 0.00001f);
  assert(adjust_weight(0.3f, -5) == 0);
  assert(adjust_weight(0, -50) == 0);
  assert(adjust_weight(9999.9f, 50) == 10000);
  assert(adjust_weight(std::numeric_limits<float>::quiet_NaN(), 1) == 0.1f);
  float weight = 7.3f;
  for (int i = 0; i < 10000; ++i) weight = adjust_weight(adjust_weight(weight, 1), -1);
  assert(std::fabs(weight - 7.3f) < 0.00001f);
  assert(weight_caption(7.3f, "kg") == "7,3 kg");
  assert(weight_caption(7.25f, "kg") == "7,25 kg");
  assert(weight_caption(0, "kg") == "0 kg");
  assert(weight_caption(10000, "lb") == "10000 lb");
  std::cout << "Exact tenth controls, bounds, drift and unchanged fractional prescriptions passed\n";
}
