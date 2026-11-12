#include "gym_native.h"
#include "muscle_mask.h"
#include <algorithm>

namespace esphome::gym_native {
namespace {
constexpr unsigned WIDTH = 384, HEIGHT = 320;
const char *NAMES[] = {"Nakke / øvre rygg", "Skuldre", "Bryst", "Øvre rygg", "Serratus",
    "Biceps", "Triceps", "Underarmer", "Mage", "Skrå magemuskler", "Korsrygg",
    "Sete", "Forside lår", "Bakside lår", "Innside lår", "Hoftebøyere", "Legger", "Forside legg"};
const char *EN_NAMES[] = {"Traps / upper back", "Shoulders", "Chest", "Upper back", "Serratus",
    "Biceps", "Triceps", "Forearms", "Abs", "Obliques", "Lower back",
    "Glutes", "Quads", "Hamstrings", "Adductors", "Hip flexors", "Calves", "Shins"};
uint16_t rgb565(uint32_t c) { return ((c >> 8) & 0xf800) | ((c >> 5) & 0x07e0) | ((c >> 3) & 0x001f); }
}

void GymNative::render_muscles() {
  if (!bound_) return;
  const bool available = valid_ && !exercises_.empty();
  if (!available) { lv_obj_add_flag(muscle_button_, LV_OBJ_FLAG_HIDDEN); return; }
  muscle_weights_.fill(0);
  for (const auto &exercise : exercises_)
    for (unsigned m = 0; m < muscle_weights_.size(); ++m)
      muscle_weights_[m] = std::max(muscle_weights_[m], exercise.muscles[m]);
  if (!muscle_pixels_.data() && !muscle_pixels_.allocate(12 + WIDTH * HEIGHT * 2)) {
    lv_obj_add_flag(muscle_button_, LV_OBJ_FLAG_HIDDEN); return;
  }
  // RLE geometry is immutable flash data. The bounded mutable RGB565 buffer is PSRAM.
  lv_image_cache_drop(&muscle_descriptor_);
  auto *pixels = reinterpret_cast<uint16_t *>(muscle_pixels_.data() + 12);
  for (const auto &run : MUSCLE_RUNS) {
    uint32_t color = run.part == 0 ? BG : 0x49515a;
    if (run.part >= 2) {
      const float weight = muscle_weights_[run.part - 2];
      if (weight >= 0.9f) color = ACCENT;
      else if (weight > 0) color = 0x72934a;
    }
    std::fill_n(pixels, run.count, rgb565(color)); pixels += run.count;
  }
  muscle_descriptor_ = {};
  muscle_descriptor_.header.magic = LV_IMAGE_HEADER_MAGIC;
  muscle_descriptor_.header.cf = LV_COLOR_FORMAT_RGB565;
  muscle_descriptor_.header.w = WIDTH; muscle_descriptor_.header.h = HEIGHT;
  muscle_descriptor_.header.stride = WIDTH * 2;
  muscle_descriptor_.data_size = WIDTH * HEIGHT * 2;
  muscle_descriptor_.data = muscle_pixels_.data() + 12;
  lv_image_set_src(muscle_image_, &muscle_descriptor_);
  lv_image_set_scale(muscle_image_, 48); // 72 x 60 inside the 112 x 64 touch target.
  lv_obj_center(muscle_image_);
  lv_obj_remove_flag(muscle_button_, LV_OBJ_FLAG_HIDDEN);
  lv_obj_invalidate(muscle_image_);
}

void GymNative::show_muscles() {
  if (!valid_ || exercises_.empty() || command_busy_ || !muscle_pixels_.data()) return;
  close_modal(); modal_kind_ = 5; binding_count_ = 128;
  modal_ = box(root_, 0, 0, 1280, 800, BG);
  label(modal_, ui_.tr("Muskler i økten", "Workout muscles"), 88, 48, 1104, 64, large_);
  label(modal_, title_.c_str(), 88, 120, 1104, 60, heading_, MUTED);
  auto *map = lv_image_create(modal_);
  lv_image_set_src(map, &muscle_descriptor_);
  lv_image_set_scale(map, 384); // Full front/back, 576 x 480 drawn pixels.
  lv_obj_set_pos(map, 184, 280); // Scaling is about the centre: drawn x88, y200.
  lv_obj_remove_flag(map, LV_OBJ_FLAG_CLICKABLE);
  auto *list = box(modal_, 712, 200, 480, 436, BG, true);
  unsigned row = 0;
  for (unsigned m = 0; m < muscle_weights_.size(); ++m) if (muscle_weights_[m] > 0) {
    label(list, ui_.english ? EN_NAMES[m] : NAMES[m], 0, row++ * 44, 456, 40, normal_,
          muscle_weights_[m] >= 0.9f ? ACCENT : MUTED);
  }
  if (!row) label(list, ui_.tr("Ingen muskeldata", "No muscle data"), 0, 0, 456, 44, normal_, MUTED);
  button(modal_, ui_.tr("Lukk", "Close"), 712, 680, 480, 72, 13);
}
}  // namespace esphome::gym_native
