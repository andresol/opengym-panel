#pragma once

#include <string>

namespace esphome::gym_native {

// Presentation only. Protocol actions, user names and notes are never translated.
struct UiText {
  bool english = false;

  const char *tr(const char *norwegian, const char *english_text) const {
    return english ? english_text : norwegian;
  }

  std::string decimal(std::string value) const {
    for (size_t i = 1; i + 1 < value.size(); ++i) {
      const char source = english ? ',' : '.';
      if (value[i] == source && value[i - 1] >= '0' && value[i - 1] <= '9' &&
          value[i + 1] >= '0' && value[i + 1] <= '9')
        value[i] = english ? '.' : ',';
    }
    return value;
  }
};

}  // namespace esphome::gym_native
