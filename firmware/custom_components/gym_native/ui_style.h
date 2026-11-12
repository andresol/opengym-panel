#pragma once
#include <cstdint>
namespace esphome::gym_native {
// One visual vocabulary for training, pickers and editors; font roles stay unchanged.
inline constexpr uint32_t BG = 0x17191b, SURFACE = 0x24272a, MUTED = 0xa8afb5;
inline constexpr uint32_t ACCENT = 0xb3f568, TEXT = 0xf6f7f8;
inline constexpr uint32_t CARD = 0x202326, RULE = 0x343a40, SELECTED = 0x2b3326;
inline constexpr uint32_t PRIMARY_TEXT = 0x17220e, PRIMARY_PRESSED = 0xc3ff83;
inline constexpr uint32_t SECONDARY_PRESSED = 0x373e43;
inline constexpr int CONTROL_RADIUS = 14, CARD_RADIUS = 20;
}  // namespace esphome::gym_native
