#include "gym_native.h"

namespace esphome::gym_native {

void GymNative::close_weight_picker() {
  if (!weight_picker_) return;
  lv_obj_delete(weight_picker_);
  weight_picker_ = nullptr;
  weight_input_ = nullptr;
  weight_apply_ = nullptr;
  weight_error_ = nullptr;
  binding_count_ = weight_binding_start_;
}

void GymNative::show_weight_picker(int manual) {
  if (command_busy_ || !valid_ || modal_kind_ != 1 || !result_labels_[0] ||
      selected_ < 0 || selected_ >= static_cast<int>(exercises_.size())) return;
  close_weight_picker();
  const auto &entry = exercises_[selected_];
  weight_binding_start_ = binding_count_;
  weight_picker_ = box(modal_, 0, 0, 1280, 800, BG);
  label(weight_picker_, ui_.tr("Velg vekt", "Choose weight"), 88, 48, 1104, 60, large_);

  if (entry.weight_step > 0 && !manual) {
    label(weight_picker_, ui_.decimal(weight_caption(editing_value_.weight, entry.unit)).c_str(),
          88, 120, 1104, 44, heading_, ACCENT);
    const auto &weights = entry.weight_options;
    for (size_t i = 0; i < weights.size(); ++i) {
      auto *choice = button(weight_picker_, ui_.decimal(weight_caption(weights[i], entry.unit)).c_str(),
                            88 + (i % 4) * 282, 184 + (i / 4) * 76,
                            258, 64, 29, i);
      lv_obj_set_style_text_font(lv_obj_get_child(choice, 0), heading_, 0);
      lv_obj_center(lv_obj_get_child(choice, 0));
      if (std::abs(weights[i] - editing_value_.weight) < 0.001f) {
        lv_obj_set_style_border_width(choice, 2, 0);
        lv_obj_set_style_border_color(choice, lv_color_hex(ACCENT), 0);
        lv_obj_set_style_text_color(lv_obj_get_child(choice, 0), lv_color_hex(ACCENT), 0);
      }
    }
    button(weight_picker_, ui_.tr("Avbryt", "Cancel"), 88, 664, 536, 72, 28);
    button(weight_picker_, ui_.tr("Egen vekt", "Custom weight"), 656, 664, 536, 72, 27, 1);
    return;
  }

  weight_entry_.reset(editing_value_.weight);
  weight_input_ = label(weight_picker_, ui_.decimal(weight_caption(editing_value_.weight, entry.unit)).c_str(),
                         372, 128, 536, 72, large_, ACCENT);
  lv_obj_set_style_text_align(weight_input_, LV_TEXT_ALIGN_CENTER, 0);
  const char *keys[] = {"1", "2", "3", "4", "5", "6", "7", "8", "9", ui_.tr(",", "."), "0", ui_.tr("Slett", "Delete")};
  for (unsigned i = 0; i < 12; ++i) {
    const int key = i == 11 ? -1 : keys[i][0];
    auto *digit = button(weight_picker_, keys[i], 372 + (i % 3) * 184,
                         224 + (i / 3) * 88, 168, 72, 30, key);
    lv_obj_set_style_text_font(lv_obj_get_child(digit, 0), heading_, 0);
    lv_obj_center(lv_obj_get_child(digit, 0));
  }
  weight_error_ = label(weight_picker_, "", 88, 584, 1104, 44, normal_, MUTED);
  button(weight_picker_, ui_.tr("Avbryt", "Cancel"), 88, 664, 536, 72, 28);
  weight_apply_ = button(weight_picker_, ui_.tr("Bruk vekt", "Use weight"), 656, 664, 536, 72, 31, 0, true);
}

void GymNative::choose_weight(int index) {
  if (command_busy_ || !valid_ || modal_kind_ != 1 || !weight_picker_ || weight_input_ ||
      selected_ < 0 || selected_ >= static_cast<int>(exercises_.size())) return;
  const auto &entry = exercises_[selected_];
  const auto &weights = entry.weight_options;
  if (index < 0 || index >= static_cast<int>(weights.size())) return;
  editing_value_.weight = weights[index];
  close_weight_picker();
  update_editor();
}

void GymNative::weight_key(int key) {
  if (command_busy_ || !valid_ || modal_kind_ != 1 || !weight_input_ ||
      selected_ < 0 || selected_ >= static_cast<int>(exercises_.size())) return;
  const bool accepted = weight_entry_.key(key);
  const auto &unit = exercises_[selected_].unit;
  lv_label_set_text(weight_input_, (weight_entry_.text.empty() ? "—" : ui_.decimal(weight_entry_.text) + " " + unit).c_str());
  lv_label_set_text(weight_error_, accepted ? "" : ("0–10000 " + unit + ui_.tr(" · maks 2 desimaler", " · max 2 decimals")).c_str());
  if (weight_entry_.valid()) lv_obj_remove_state(weight_apply_, LV_STATE_DISABLED);
  else lv_obj_add_state(weight_apply_, LV_STATE_DISABLED);
}

void GymNative::use_weight() {
  if (command_busy_ || !valid_ || modal_kind_ != 1 || !weight_input_ || !weight_entry_.valid() ||
      selected_ < 0 || selected_ >= static_cast<int>(exercises_.size())) return;
  editing_value_.weight = weight_entry_.value();
  close_weight_picker();
  update_editor();
}

}  // namespace esphome::gym_native
