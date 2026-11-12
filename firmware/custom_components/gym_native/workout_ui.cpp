#include "gym_native.h"
#include <cmath>
#include <cstdio>
#include "esp_random.h"

namespace esphome::gym_native {
namespace {
void caption(lv_obj_t *object, const std::string &value) {
  if (object && value != lv_label_get_text(object)) lv_label_set_text(object, value.c_str());
}
void visible(lv_obj_t *object, bool value) {
  if (value) lv_obj_remove_flag(object, LV_OBJ_FLAG_HIDDEN);
  else lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
}
void enabled(lv_obj_t *object, bool value) {
  if (value) lv_obj_remove_state(object, LV_STATE_DISABLED);
  else lv_obj_add_state(object, LV_STATE_DISABLED);
}
}

void GymNative::render_session() {
  if (!bound_) return;
  const bool active = !session_id_.empty();
  const bool has_status = lv_label_get_text(status_label_)[0] != '\0';
  // Anchor both control rows to the drawn image, not its wider invisible stage.
  // Each outer edge extends 20 px beyond the image; paired actions keep 24 px air.
  const int image_left = lv_obj_get_style_x(media_stage_, LV_PART_MAIN) +
      (lv_obj_get_style_width(media_stage_, LV_PART_MAIN) - image_display_width_) / 2;
  const int left = image_left - 20;
  const int span = image_display_width_ + 40;
  const int first_width = (span - 24) / 2;
  const int second_left = left + first_width + 24;
  const int second_width = span - 24 - first_width;
  const int action_width = active ? first_width : span;
  lv_obj_set_x(session_button_, left);
  lv_obj_set_width(session_button_, action_width);
  lv_obj_set_width(session_text_, action_width - 16);
  lv_obj_center(session_text_);
  const auto resize_second = [&](lv_obj_t *button) {
    lv_obj_set_x(button, second_left);
    lv_obj_set_width(button, second_width);
    auto *text = lv_obj_get_child(button, 0);
    lv_obj_set_width(text, second_width - 16);
    lv_obj_center(text);
  };
  resize_second(set_button_);
  resize_second(controls_[1]);
  lv_obj_set_x(controls_[0], left);
  lv_obj_set_width(controls_[0], first_width);
  auto *previous_text = lv_obj_get_child(controls_[0], 0);
  lv_obj_set_width(previous_text, first_width - 16);
  lv_obj_center(previous_text);
  visible(brand_label_, !has_status);
  visible(date_label_, !active && !has_status);
  visible(session_label_, active && !has_status);
  visible(volume_title_, active && valid_ && !has_status);
  visible(volume_label_, active && valid_ && !has_status);
  caption(volume_label_, ui_.decimal(weight_caption(session_volume_, volume_unit_)));
  visible(session_button_, person_ >= 0 && !(valid_ && exercises_.empty() && session_id_.empty()));
  enabled(session_button_, plan_fresh() && !command_busy_ && (active || !exercises_.empty() || !routine_choices_.empty()));
  const bool complete = valid_ && active && session_phase_ == "active" && session_total_ > 0 &&
      session_done_ == session_total_ && all_exercises_complete(exercises_);
  const bool session_primary = !active || complete;
  if (session_button_primary_ != session_primary) {
    style_button(session_button_, session_primary); session_button_primary_ = session_primary;
  }
  style_button(set_button_, !complete);
  caption(session_text_, command_busy_ ? ui_.tr("Venter …", "Please wait …") : active ? session_phase_ == "saving" ? ui_.tr("Lagrer økt …", "Saving workout …") : ui_.tr("Avslutt økt", "Finish workout") : exercises_.empty() && !routine_choices_.empty() ? ui_.tr("Velg økt", "Choose workout") : ui_.tr("Start økt", "Start workout"));
  visible(set_button_, valid_ && active && session_phase_ == "active" && !exercises_.empty());
  const auto progress = exercises_.empty() ? WorkoutProgress{} : workout_progress(exercises_[selected_].sets);
  enabled(set_button_, plan_fresh() && !command_busy_ && progress.next_row >= 0);
  caption(lv_obj_get_child(set_button_, 0), progress.complete() ? ui_.tr("Øvelse fullført", "Exercise complete") : ui_.tr("Registrer sett", "Log set"));
  if (active && !exercises_.empty()) caption(position_label_, ui_.tr("ØVELSE ", "EXERCISE ") + std::to_string(selected_ + 1) +
      ui_.tr(" AV ", " OF ") + std::to_string(exercises_.size()) + " · " + progress.next_caption(ui_));
  for (auto *day : days_) enabled(day, !active && !command_busy_);
  std::string summary;
  if (active && valid_) {
    const unsigned seconds = static_cast<unsigned>(std::min(31536000.0, session_elapsed_ + (millis() - elapsed_received_) / 1000.0));
    char time[24]; snprintf(time, sizeof(time), "%02u:%02u", seconds / 60, seconds % 60);
    summary = std::string(time) + " · " + std::to_string(session_done_) + "/" +
        std::to_string(session_total_) + ui_.tr(" sett", " sets");
    if (session_phase_ == "saving") summary = paired_ ? ui_.tr("Lagrer i OpenGym …", "Saving to OpenGym …") : ui_.tr("Lagring venter på tilkobling", "Waiting to reconnect before saving");
  }
  caption(session_label_, summary);
}

void GymNative::session_action() {
  if (!valid_ || command_busy_ || person_ < 0) return;
  if (session_id_.empty() && exercises_.empty()) { show_routines(); return; }
  if (!paired_) { show_pair(); return; }
  if (session_id_.empty()) submit("start");
  else if (session_phase_ == "saving") submit("finish");
  else show_finish();
}

void GymNative::render_rest_day() {
  const bool resting = valid_ && session_id_.empty() && exercises_.empty();
  visible(rest_page_, resting);
  if (!resting) return;
  lv_obj_move_foreground(rest_page_);
  caption(rest_heading_, routine_choices_.empty() ? ui_.tr("Hviledag", "Rest day") : ui_.tr("Dine økter", "Your workouts"));
  visible(rest_empty_, routine_choices_.empty());
  lv_obj_clean(rest_list_);
  binding_count_ = 192;  // Independent of modal bindings (128..191).
  for (size_t i = 0; i < routine_choices_.size(); ++i) {
    auto *tile = button(rest_list_, routine_choices_[i].name.c_str(), (i % 2) * 564,
                        (i / 2) * 154, 540, 138, 23, i);
    lv_obj_set_style_bg_color(tile, lv_color_hex(CARD), 0);
    lv_obj_set_style_radius(tile, CARD_RADIUS, 0);
    lv_obj_set_style_border_width(tile, 1, 0);
    lv_obj_set_style_border_color(tile, lv_color_hex(RULE), 0);
    auto *name = lv_obj_get_child(tile, 0);
    lv_obj_set_style_text_font(name, heading_, 0);
    lv_obj_set_style_text_align(name, LV_TEXT_ALIGN_LEFT, 0);
    lv_obj_set_width(name, 492);
    lv_obj_set_height(name, 80);
    lv_label_set_long_mode(name, LV_LABEL_LONG_DOT);
    lv_obj_align(name, LV_ALIGN_LEFT_MID, 24, 0);
  }
  lv_obj_scroll_to_y(rest_list_, 0, LV_ANIM_OFF);
}

void GymNative::show_routines() {
  if (!valid_ || command_busy_ || !session_id_.empty() || routine_choices_.empty()) return;
  close_modal(); modal_kind_ = 4; binding_count_ = 128;
  modal_ = box(root_, 0, 0, 1280, 800, BG);
  label(modal_, ui_.tr("Velg økt", "Choose workout"), 220, 60, 840, 70, large_);
  label(modal_, people_[person_].name.c_str(), 220, 145, 840, 45, heading_, ACCENT);
  auto *list = box(modal_, 220, 218, 840, 380, BG, true);
  for (size_t i = 0; i < routine_choices_.size(); ++i) {
    auto *b = button(list, routine_choices_[i].name.c_str(), 0, i * 96, 820, 84, 23, i);
    auto *name = lv_obj_get_child(b, 0);
    lv_obj_set_style_text_align(name, LV_TEXT_ALIGN_LEFT, 0);
    lv_obj_set_width(name, 772);
    lv_obj_set_height(name, 56);
    lv_label_set_long_mode(name, LV_LABEL_LONG_DOT);
    lv_obj_align(name, LV_ALIGN_LEFT_MID, 24, 0);
    if (routine_choices_[i].key == selected_routine_) {
      lv_obj_set_style_border_width(b, 2, 0);
      lv_obj_set_style_border_color(b, lv_color_hex(ACCENT), 0);
    }
  }
  button(modal_, ui_.tr("Avbryt", "Cancel"), 220, 659, 240, 65, 13);
}

void GymNative::choose_routine(int index) {
  if (!valid_ || command_busy_ || (modal_kind_ != 4 && !(!modal_kind_ && exercises_.empty())) || !session_id_.empty() ||
      index < 0 || index >= static_cast<int>(routine_choices_.size())) return;
  const std::string key = routine_choices_[index].key;
  close_modal();
  lock_request(); wanted_routine_ = key; wanted_day_ = day_; ++context_; unlock_request();
  clear_plan(ui_.tr("Henter økt …", "Loading workout …"));
}

void GymNative::close_modal() {
  if (command_busy_) return;
  close_weight_picker();
  if (modal_) lv_obj_delete(modal_);
  modal_ = nullptr; modal_message_ = nullptr; pair_label_ = nullptr;
  modal_connection_message_ = false;
  result_labels_.fill(nullptr); modal_kind_ = 0; pair_code_.clear();
  for (auto &buttons : step_buttons_) buttons.fill(nullptr);
}

void GymNative::show_finish() {
  if (command_busy_ || session_id_.empty()) return;
  close_modal(); modal_kind_ = 2; binding_count_ = 128;
  modal_ = box(root_, 0, 0, 1280, 800, BG);
  label(modal_, ui_.tr("Avslutte økten?", "Finish this workout?"), 240, 165, 800, 70, large_);
  const auto summary = std::to_string(session_done_) + ui_.tr(" av ", " of ") + std::to_string(session_total_) + ui_.tr(" sett registrert", " sets logged");
  label(modal_, summary.c_str(), 240, 258, 800, 50, heading_, ACCENT);
  label(modal_, session_done_ ? ui_.tr("Bare utførte sett lagres i OpenGym.", "Only completed sets are saved to OpenGym.") : ui_.tr("Ingen utførte sett. Økten avsluttes uten historikk.", "No completed sets. Nothing will be saved."),
        240, 328, 800, 65, normal_, MUTED);
  modal_message_ = label(modal_, "", 240, 414, 800, 60, normal_, MUTED);
  button(modal_, ui_.tr("Fortsett økt", "Continue workout"), 240, 505, 248, 70, 13);
  button(modal_, ui_.tr("Forkast økt", "Discard workout"), 512, 505, 248, 70, 18);
  button(modal_, session_done_ ? ui_.tr("Lagre og avslutt", "Save and finish") : ui_.tr("Avslutt uten lagring", "Finish without saving"), 784, 505, 272, 70, 17, 0, true);
}

void GymNative::show_pair() {
  if (command_busy_ || person_ < 0) return;
  close_modal(); modal_kind_ = 3; binding_count_ = 128;
  modal_ = box(root_, 0, 0, 1280, 800, BG);
  const auto title = ui_.tr("Koble til ", "Pair ") + people_[person_].name;
  label(modal_, title.c_str(), 220, 45, 840, 60, large_);
  label(modal_, ui_.tr("Åpne OpenGym med samme person på mobilen.\nSettings → Pair the mobile app. Skriv inn koden her.", "Open the same profile in OpenGym on your phone.\nSettings → Pair the mobile app. Enter the code here."),
        220, 128, 840, 72, normal_, MUTED);
  pair_label_ = label(modal_, "— — — — — — — —", 220, 215, 840, 58, large_, ACCENT);
  static const char alphabet[] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  for (unsigned i = 0; i < 32; ++i) {
    char key[2] = {alphabet[i], 0};
    button(modal_, key, 220 + (i % 8) * 106, 300 + (i / 8) * 67, 96, 57, 20, alphabet[i]);
  }
  modal_message_ = label(modal_, "", 220, 580, 840, 54, normal_, MUTED);
  button(modal_, ui_.tr("Lukk", "Close"), 220, 659, 240, 65, 13);
  button(modal_, ui_.tr("Slett", "Delete"), 492, 659, 240, 65, 21);
  button(modal_, ui_.tr("Koble til", "Pair"), 764, 659, 296, 65, 19, 0, true);
}

void GymNative::next_set() {
  if (!valid_ || command_busy_ || session_phase_ != "active" || exercises_.empty()) return;
  const auto progress = workout_progress(exercises_[selected_].sets);
  if (progress.next_row >= 0) {
    edit_set(progress.next_row * 3 + progress.next_side); return;
  }
  update_status(ui_.tr("Alle sett i denne øvelsen er registrert", "All sets for this exercise are logged"));
}

void GymNative::edit_set(int encoded) {
  if (!valid_ || command_busy_ || session_phase_ != "active" || exercises_.empty() || encoded < 0) return;
  const auto &e = exercises_[selected_];
  const int row = encoded / 3, side = encoded % 3;
  if (row >= static_cast<int>(e.sets.size()) || (e.sets[row].per_side ? side == 0 : side != 0)) return;
  close_modal(); modal_kind_ = 1; binding_count_ = 128;
  editing_row_ = row; editing_side_ = side; editing_revision_ = session_revision_;
  editing_value_ = side == 1 ? e.sets[row].left : side == 2 ? e.sets[row].right : e.sets[row].value;
  modal_ = box(root_, 0, 0, 1280, 800, BG);
  auto *exercise_title = label(modal_, e.name.c_str(), 88, 48, 1104, 104, large_);
  lv_obj_set_height(exercise_title, LV_SIZE_CONTENT);
  lv_obj_update_layout(exercise_title);
  const int title_height = std::min(104, static_cast<int>(lv_obj_get_height(exercise_title)));
  lv_obj_set_height(exercise_title, title_height);
  lv_label_set_long_mode(exercise_title, LV_LABEL_LONG_DOT);
  const auto title = e.rows[row].name +
      (side == 1 ? ui_.tr(" · Venstre", " · Left") : side == 2 ? ui_.tr(" · Høyre", " · Right") : "");
  label(modal_, title.c_str(), 88, 48 + title_height + 16, 1104, 44, heading_, ACCENT);
  editing_steps_.fill(1);
  const int fields[] = {e.mode == "cardio" ? 1 : 0, e.mode == "cardio" ? 2 : 1};
  for (int line = 0; line < 2; ++line) {
    const int field = fields[line];
    auto *card = box(modal_, 88 + line * 568, 224, 536, 328, CARD);
    lv_obj_set_style_radius(card, CARD_RADIUS, 0);
    lv_obj_set_style_border_width(card, 1, 0);
    lv_obj_set_style_border_color(card, lv_color_hex(RULE), 0);
    const char *name = field == 0 ? ui_.tr("VEKT", "WEIGHT") : field == 2 ? ui_.tr("HASTIGHET", "SPEED") :
        e.mode == "time" ? ui_.tr("TID", "TIME") : e.mode == "cardio" ? ui_.tr("VARIGHET", "DURATION") : ui_.tr("REPETISJONER", "REPS");
    label(card, name, 32, 24, 472, 30, normal_, MUTED);
    if (field == 0) {
      auto *value_button = button(card, "", 132, 96, 272, 80, 27);
      result_labels_[field] = lv_obj_get_child(value_button, 0);
      lv_obj_set_style_text_font(result_labels_[field], large_, 0);
      lv_obj_set_size(result_labels_[field], 256, 80);
      lv_obj_center(result_labels_[field]);
    } else {
      result_labels_[field] = label(card, "", 132, 96, 272, 80, large_);
    }
    lv_obj_set_style_text_align(result_labels_[field], LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_pad_top(result_labels_[field], (80 - lv_font_get_line_height(large_)) / 2, 0);
    auto *minus = button(card, "−", 32, 96, 88, 80, 24, -(field + 1));
    auto *plus = button(card, "+", 416, 96, 88, 80, 24, field + 1);
    lv_obj_set_style_text_font(lv_obj_get_child(minus, 0), heading_, 0);
    lv_obj_set_style_text_font(lv_obj_get_child(plus, 0), heading_, 0);
    lv_obj_center(lv_obj_get_child(minus, 0));
    lv_obj_center(lv_obj_get_child(plus, 0));
    label(card, ui_.tr("Trinn", "Step"), 32, 204, 472, 24, small_, MUTED);
    const auto steps = field == 0 && e.weight_step > 0 ? std::vector<int>{1} : result_steps(field, e.mode);
    const char *weight_steps[] = {"0,1", "0,5", "1", "5"};
    const char *reps_steps[] = {"1", "5", "10"};
    const char *time_steps[] = {ui_.tr("5 sek", "5 sec"), ui_.tr("15 sek", "15 sec"), ui_.tr("30 sek", "30 sec")};
    const char *minute_steps[] = {ui_.tr("0,5 min", "0.5 min"), "1 min", "5 min"};
    const char *speed_steps[] = {"0,1", "0,5", "1"};
    for (size_t i = 0; i < steps.size(); ++i) {
      std::string key = field == 0 && e.weight_step > 0 ? "1 plate" :
          field == 0 ? std::string(weight_steps[i]) + " " + e.unit : field == 2 ? speed_steps[i] :
          e.mode == "time" ? time_steps[i] : e.mode == "cardio" ? minute_steps[i] : reps_steps[i];
      const bool four_steps = steps.size() == 4;
      step_buttons_[field][i] = button(card, key.c_str(), 32 + i * (four_steps ? 121 : 162), 240,
                                      four_steps ? 109 : i == 2 ? 148 : 146,
                                      56, 25, (field + 1) * 100 + steps[i]);
    }
  }
  modal_message_ = label(modal_, "", 88, 574, 1104, 48, normal_, MUTED);
  button(modal_, ui_.tr("Avbryt", "Cancel"), 88, 648, editing_value_.done ? 252 : 536, 72, 13);
  if (editing_value_.done) button(modal_, ui_.tr("Angre sett", "Undo set"), 372, 648, 252, 72, 16);
  button(modal_, editing_value_.done ? ui_.tr("Lagre endring", "Save changes") : ui_.tr("Registrer sett", "Log set"), 656, 648, 536, 72, 15, 0, true);
  update_editor();
}

void GymNative::step_result(int encoded) {
  const int field = std::abs(encoded) - 1;
  if (field < 0 || field > 2) return;
  const int amount = (field + 1) * 100 + editing_steps_[field];
  adjust_result(encoded < 0 ? -amount : amount);
}

void GymNative::select_result_step(int encoded) {
  if (command_busy_ || modal_kind_ != 1 || exercises_.empty()) return;
  const int field = encoded / 100 - 1, step = encoded % 100;
  if (field < 0 || field > 2 || !result_labels_[field]) return;
  const auto &entry = exercises_[selected_];
  const auto allowed = field == 0 && entry.weight_step > 0 ? std::vector<int>{1} : result_steps(field, entry.mode);
  if (std::find(allowed.begin(), allowed.end(), step) == allowed.end()) return;
  editing_steps_[field] = step;
  update_editor();
}

void GymNative::adjust_result(int encoded) {
  if (command_busy_ || modal_kind_ != 1 || exercises_.empty()) return;
  const auto &e = exercises_[selected_];
  const int field = std::abs(encoded) / 100 - 1;
  const float delta = (encoded < 0 ? -1 : 1) * (std::abs(encoded) % 100);
  auto adjust = [delta](float &value, float step, float maximum) {
    value = std::round(std::max(0.0f, std::min(maximum, value + delta * step)) * 10) / 10;
  };
  if (field == 0 && e.weight_step > 0) editing_value_.weight =
      adjust_stack_weight(editing_value_.weight, delta > 0 ? 1 : -1, e.weight_options);
  else if (field == 0) editing_value_.weight = adjust_weight(editing_value_.weight, static_cast<int>(delta));
  else if (field == 2) adjust(editing_value_.speed, 0.1f, 100);
  else if (e.mode == "time") adjust(editing_value_.seconds, 5, 7200);
  else if (e.mode == "cardio") adjust(editing_value_.minutes, 0.5f, 1440);
  else adjust(editing_value_.reps, 1, 1000);
  update_editor();
}

void GymNative::update_editor() {
  const auto &e = exercises_[selected_];
  char value[96];
  caption(result_labels_[0], ui_.decimal(weight_caption(editing_value_.weight, e.unit)));
  if (e.mode == "time") snprintf(value, sizeof(value), ui_.tr("%.0f sek", "%.0f sec"), editing_value_.seconds);
  else if (e.mode == "cardio") snprintf(value, sizeof(value), "%s", ui_.decimal(weight_caption(editing_value_.minutes, "min")).c_str());
  else snprintf(value, sizeof(value), "%.0f reps", editing_value_.reps);
  caption(result_labels_[1], value);
  caption(result_labels_[2], ui_.decimal(weight_caption(editing_value_.speed, ui_.tr("km/t", "km/h"))));
  for (int field = 0; field < 3; ++field) {
    const auto steps = field == 0 && e.weight_step > 0 ? std::vector<int>{1} : result_steps(field, e.mode);
    for (size_t i = 0; i < steps.size(); ++i) if (step_buttons_[field][i]) {
      auto *b = step_buttons_[field][i];
      const bool selected = editing_steps_[field] == steps[i];
      lv_obj_set_style_bg_color(b, lv_color_hex(selected ? SELECTED : SURFACE), 0);
      lv_obj_set_style_border_width(b, selected ? 2 : 1, 0);
      lv_obj_set_style_border_color(b, lv_color_hex(selected ? ACCENT : RULE), 0);
      lv_obj_set_style_text_color(lv_obj_get_child(b, 0), lv_color_hex(selected ? ACCENT : TEXT), 0);
    }
  }
}

void GymNative::submit_result(bool done) {
  if (modal_kind_ != 1 || weight_picker_) return;
  submit("set", done);
}

void GymNative::apply_set_feedback() {
  if (!set_feedback_.pending || command_busy_) return;
  if (!valid_ || selected_ < 0 || selected_ >= static_cast<int>(exercises_.size()) ||
      set_feedback_.row < 0 || set_feedback_.row >= static_cast<int>(exercises_[selected_].sets.size())) {
    set_feedback_.cancel(); return;
  }
  const auto &e = exercises_[selected_];
  const auto &row = e.sets[set_feedback_.row];
  const bool target_done = set_feedback_.side == 1 ? row.left.done : set_feedback_.side == 2 ? row.right.done : row.value.done;
  const bool complete = row.per_side ? row.left.done && row.right.done : row.value.done;
  const auto effect = set_feedback_.observe(session_id_, session_revision_, selected_, session_phase_ == "active",
                                            target_done, complete, millis());
  if (effect.follow) {
    if (modal_kind_ == 1) close_modal();
    update_status("");
    int last_row = -1, count = 0;
    for (size_t i = 0; i < e.sets.size(); ++i) {
      count += e.sets[i].per_side ? 2 : 1;
      if (static_cast<int>(i) == set_feedback_.row) last_row = count - 1;
    }
    lv_obj_update_layout(rows_);
    lv_obj_scroll_to_y(rows_, follow_set_scroll(last_row, count, lv_obj_get_style_height(rows_, LV_PART_MAIN)), LV_ANIM_OFF);
    ++automatic_follows_;
  }
  if (effect.rest) {
    timer_.reset(e.rest);
    timer_.toggle(millis(), e.rest);
    if (timer_.running) ++automatic_rests_;
    render_timer();
    // Only a newly confirmed final set advances. Editing a completed result,
    // undo, stale/error replies and one side of a pair must not move the view.
    if (workout_progress(e.sets).complete()) {
      const int next = next_pending_exercise(exercises_, selected_);
      if (next >= 0) {
        choose_exercise(next);  // Keeps the just-started rest deadline intact.
        render_session();
      }
    }
  }
}

void GymNative::submit(const std::string &action, bool done) {
  if (command_busy_ || !valid_ || person_ < 0) return;
  if (!allow_submission()) return;
  if (action == "pair" && pair_code_.size() != 8) {
    caption(modal_message_, ui_.tr("Skriv inn alle 8 tegnene", "Enter all 8 characters")); return;
  }
  if ((action == "set" || action == "finish" || action == "discard") && session_id_.empty()) return;
  if (action == "start" && !session_id_.empty()) return;
  if (action == "set" && (selected_ < 0 || selected_ >= static_cast<int>(exercises_.size()) ||
      editing_row_ < 0 || editing_row_ >= static_cast<int>(exercises_[selected_].sets.size()))) {
    close_modal(); update_status(ui_.tr("Økten er oppdatert · prøv igjen", "Workout updated · try again"), true); return;
  }
  char nonce[40]; snprintf(nonce, sizeof(nonce), "%08lx%08lx%08lx%08lx",
      static_cast<unsigned long>(esp_random()), static_cast<unsigned long>(esp_random()),
      static_cast<unsigned long>(esp_random()), static_cast<unsigned long>(esp_random()));
  const std::string payload = json::build_json([&](JsonObject root) {
    root["action"] = action; root["requestId"] = nonce; root["day"] = day_;
    if ((action == "start" || action == "pair") && !selected_routine_.empty()) root["routine"] = selected_routine_;
    if (action == "pair") root["code"] = pair_code_;
    if (!session_id_.empty()) {
      root["sessionId"] = session_id_;
      root["revision"] = action == "set" ? editing_revision_ : session_revision_;
    }
    if (action == "set") {
      root["exercise"] = selected_; root["row"] = editing_row_; root["done"] = done;
      if (editing_side_) root["side"] = editing_side_ == 1 ? "L" : "R";
      const auto &e = exercises_[selected_];
      if (e.mode != "cardio") root["weight"] = editing_value_.weight;
      if (e.mode == "time") root["seconds"] = static_cast<unsigned>(editing_value_.seconds);
      else if (e.mode == "cardio") { root["minutes"] = editing_value_.minutes; root["speed"] = editing_value_.speed; }
      else root["reps"] = static_cast<unsigned>(editing_value_.reps);
    }
  });
  set_feedback_.cancel();
  if (action == "set") {
    const auto &row = exercises_[selected_].sets[editing_row_];
    const bool complete = row.per_side ? row.left.done && row.right.done : row.value.done;
    set_feedback_.arm(session_id_, editing_revision_, selected_, editing_row_, editing_side_, done, complete, millis());
  }
  command_busy_ = true; command_action_ = action;
  lock_request(); wanted_command_ = payload; unlock_request();
  update_status(action == "finish" ? ui_.tr("Lagrer økten i OpenGym …", "Saving workout to OpenGym …") : ui_.tr("Venter på bekreftelse …", "Waiting for confirmation …"));
  caption(modal_message_, action == "finish" ? ui_.tr("Lagrer økten i OpenGym …", "Saving workout to OpenGym …") : ui_.tr("Venter på bekreftelse …", "Waiting for confirmation …"));
  render_session();
}
}  // namespace esphome::gym_native
