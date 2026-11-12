#pragma once
#include <algorithm>
#include <vector>
#include <cmath>
#include <cstdio>
#include <string>

namespace esphome::gym_native {
inline bool valid_stack_weights(const std::vector<float> &weights) {
  if (weights.size() < 2 || weights.size() > 24 || weights.front() != 0) return false;
  for (size_t i = 0; i < weights.size(); ++i) {
    if (!std::isfinite(weights[i]) || weights[i] < 0 || weights[i] > 2000 ||
        (i > 0 && weights[i] <= weights[i - 1])) return false;
  }
  return true;
}
inline std::vector<int> result_steps(int field, const std::string &mode) {
  if (field == 0) return {1, 5, 10, 50};    // 0.1 / 0.5 / 1 / 5 kg or lb
  if (field == 2) return {1, 5, 10};        // 0.1 / 0.5 / 1 km/h
  if (mode == "time") return {1, 3, 6};    // 5 / 15 / 30 seconds
  if (mode == "cardio") return {1, 2, 10}; // 0.5 / 1 / 5 minutes
  return {1, 5, 10};                       // 1 / 5 / 10 repetitions
}

// Integer tenths avoid cumulative float drift; only explicit adjustment snaps
// a prescription to tenths. Merely opening/saving retains e.g. 7.25 kg.
inline float adjust_weight(float value, int tenths) {
  if (!std::isfinite(value)) value = 0;
  const int current = static_cast<int>(std::lround(std::clamp(value, 0.0f, 10000.0f) * 10));
  return std::clamp(current + tenths, 0, 100000) / 10.0f;
}

// Select the next printed load, including from a historical off-grid result.
inline float adjust_stack_weight(float value, int direction, const std::vector<float> &weights) {
  if (!std::isfinite(value)) value = 0;
  if (!valid_stack_weights(weights)) return value;
  if (direction > 0) {
    for (float weight : weights) if (weight > value + 0.001f) return weight;
    return weights.back();
  }
  for (auto it = weights.rbegin(); it != weights.rend(); ++it) if (*it < value - 0.001f) return *it;
  return weights.front();
}

inline std::string weight_caption(float value, const std::string &unit) {
  char buffer[32];
  std::snprintf(buffer, sizeof(buffer), "%.2f", static_cast<double>(value));
  std::string number(buffer);
  while (!number.empty() && number.back() == '0') number.pop_back();
  if (!number.empty() && number.back() == '.') number.pop_back();
  for (auto &c : number) if (c == '.') c = ',';
  return unit.empty() ? number : number + " " + unit;
}

// Local keypad draft: opening/cancelling never changes the set. Untouched
// prescriptions retain their original precision; typed values use hundredths.
struct WeightEntry {
  std::string text;
  float original = 0;
  bool edited = false;
  bool replace = true;

  void reset(float value) {
    original = std::isfinite(value) ? std::clamp(value, 0.0f, 10000.0f) : 0;
    text = weight_caption(original, "");
    edited = false;
    replace = true;
  }

  static int hundredths(const std::string &input) {
    int whole = 0, fraction = 0, digits = 0;
    bool decimal = false;
    for (char c : input) {
      if (c == ',') { decimal = true; continue; }
      if (decimal) { fraction = fraction * 10 + c - '0'; ++digits; }
      else whole = whole * 10 + c - '0';
    }
    return whole * 100 + (digits == 1 ? fraction * 10 : fraction);
  }

  bool key(int key) {
    if (key == -1) {
      if (!text.empty()) text.pop_back();
      edited = true;
      replace = false;
      return true;
    }
    if (key != ',' && (key < '0' || key > '9')) return false;
    std::string next = replace ? "" : text;
    if (key == ',') {
      if (next.find(',') != std::string::npos) return false;
      if (next.empty()) next = "0";
    }
    next += static_cast<char>(key);
    const auto comma = next.find(',');
    if (next.size() > 8 || (comma != std::string::npos && next.size() - comma - 1 > 2) ||
        hundredths(next) > 1000000) return false;
    text = next;
    edited = true;
    replace = false;
    return true;
  }

  bool valid() const { return !text.empty(); }
  float value() const { return edited ? hundredths(text) / 100.0f : original; }
};

}  // namespace esphome::gym_native
