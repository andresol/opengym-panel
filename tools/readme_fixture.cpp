// Offline documentation fixture. The widget methods are injected unchanged
// from production source by render_readme.py. No network or device libraries.
#include "lvgl.h"
#include "ui_style.h"
#include "person_handoff.h"
#include "workout_progress.h"
#include "set_feedback.h"
#include "weight_control.h"
#include "timer.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
using namespace esphome::gym_native;
uint32_t millis() { return 1000; }
void set_text(lv_obj_t *object, const std::string &value) { lv_label_set_text(object, value.c_str()); }
void caption(lv_obj_t *object, const std::string &value) { set_text(object, value); }
void hidden(lv_obj_t *object, bool hide) {
  if (hide) lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
  else lv_obj_remove_flag(object, LV_OBJ_FLAG_HIDDEN);
}
void visible(lv_obj_t *object, bool show) { hidden(object, !show); }
void enabled(lv_obj_t *object, bool enable) {
  if (enable) lv_obj_remove_state(object, LV_STATE_DISABLED);
  else lv_obj_add_state(object, LV_STATE_DISABLED);
}
/* FONT_DATA */
/* STRUCTURES */
class GymNative {
 public:
  struct Binding { GymNative *owner; int action, value; };
  std::array<Binding, 224> bindings_{};
  unsigned binding_count_ = 0;
  const lv_font_t *small_, *normal_, *heading_, *large_, *exercise_font_;
  bool bound_ = false, valid_ = true, command_busy_ = false, paired_ = true;
  bool session_button_primary_ = true;
  int selected_ = 0, day_ = 0, person_ = 0, image_display_width_ = 512;
  unsigned session_done_ = 1, session_total_ = 24;
  double session_elapsed_ = 432;
  uint32_t elapsed_received_ = 1000;
  float session_volume_ = 160;
  std::string volume_unit_ = "kg", date_ = "2026-01-05", title_ = "Helkropp A";
  std::string session_id_, session_phase_ = "active", selected_routine_;
  std::vector<RoutineChoice> routine_choices_;
  std::vector<Person> people_{{"alex", "Alex"}, {"blair", "Blair"},
                              {"casey", "Casey"}, {"drew", "Drew"}};
  std::vector<Exercise> exercises_;
  std::array<bool, 7> week_{{true, false, true, false, true, false, false}};
  std::array<lv_obj_t *, 7> days_{};
  std::array<lv_obj_t *, 6> controls_{};
  std::vector<lv_obj_t *> exercise_buttons_, exercise_done_labels_;
  esphome::gym_panel::Timer timer_;
  SetScroll set_scroll_;
  lv_obj_t *root_, *welcome_, *welcome_status_, *welcome_heading_, *people_list_;
  lv_obj_t *brand_label_, *date_label_, *person_button_, *person_text_;
  lv_obj_t *session_label_, *volume_title_, *volume_label_, *workout_;
  lv_obj_t *routine_label_, *muscle_button_, *muscle_image_, *exercise_list_, *exercise_more_;
  lv_obj_t *routine_button_, *position_label_, *exercise_label_, *media_stage_, *media_empty_;
  lv_obj_t *media_viewport_, *media_image_, *media_hit_area_, *note_scroller_, *note_label_;
  lv_obj_t *set_count_, *target_label_, *load_label_, *detail_label_, *rows_;
  lv_obj_t *timer_label_, *timer_button_, *timer_text_, *session_button_, *session_text_;
  lv_obj_t *status_label_, *set_button_, *rest_page_, *rest_heading_, *rest_empty_, *rest_list_;
  lv_obj_t *box(lv_obj_t *, int, int, int, int, uint32_t, bool = false);
  lv_obj_t *label(lv_obj_t *, const char *, int, int, int, int, const lv_font_t *, uint32_t = TEXT);
  lv_obj_t *button(lv_obj_t *, const char *, int, int, int, int, int, int = 0, bool = false);
  void style_button(lv_obj_t *, bool);
  void begin(const lv_font_t *, const lv_font_t *, const lv_font_t *, const lv_font_t *, const lv_font_t *);
  void render_plan();
  void render_exercise();
  void render_timer();
  void render_session();
  void update_exercise_overflow();
  static void exercise_scroll(lv_event_t *);
  static void click(lv_event_t *) {}
  bool plan_fresh() const { return true; }
  void render_rest_day() {}
  void render_people() { lv_obj_clean(people_list_); /* PEOPLE */ }
};
/* METHODS */

void snapshot(lv_obj_t *root, const char *name) {
  lv_obj_update_layout(root);
  auto *buffer = lv_snapshot_take(root, LV_COLOR_FORMAT_RGB888);
  assert(buffer);
  FILE *file = fopen(name, "wb");
  assert(file);
  fwrite(buffer->data, 1, buffer->data_size, file);
  fclose(file);
  printf("snapshot %s %u %u %u\n", name, buffer->header.w, buffer->header.h, buffer->header.stride);
  lv_draw_buf_destroy(buffer);
}

int main() {
  lv_init();
  /* FONT_INIT */
  auto *display = lv_display_create(1280, 800);
  auto *root = lv_screen_active();
  lv_obj_remove_style_all(root);
  lv_obj_set_style_bg_opa(root, LV_OPA_COVER, 0);
  GymNative gym;
  gym.begin(&f16, &f20, &f30, &f42, &f18);
  set_text(gym.status_label_, "");
  hidden(gym.status_label_, true);
  gym.render_people();
  snapshot(root, "profiles.rgb");

  hidden(gym.welcome_, true);
  hidden(gym.workout_, false);
  hidden(gym.person_button_, false);
  set_text(gym.person_text_, "Alex");
  const char *names[] = {"Stangknebøy", "Manualbenk", "Sittende kabelroing",
                         "Nedtrekk", "Sidehev med manualer", "Dead bug"};
  for (auto name : names) {
    Exercise exercise;
    exercise.name = name;
    exercise.target = "3 × 8";
    exercise.load = "50 kg";
    exercise.detail = "1 oppvarmingssett · Pause 90 sek";
    exercise.note = "Eksempeldata · kontrollert teknikk og rolig tempo.";
    exercise.mode = "reps";
    exercise.unit = "kg";
    exercise.rest = 90;
    exercise.work_sets = 3;
    for (int row = 0; row < 4; ++row) {
      exercise.rows.push_back({row ? "Sett " + std::to_string(row) : "Oppv. 1",
                              row ? "50 kg" : "20 kg", "8 reps"});
      Exercise::Set set;
      set.warmup = row == 0;
      set.value.weight = row ? 50 : 20;
      set.value.reps = 8;
      set.value.done = row == 0 && gym.exercises_.empty();
      exercise.sets.push_back(set);
    }
    gym.exercises_.push_back(exercise);
  }
  gym.session_id_ = "synthetic-readme-session";
  gym.timer_.reset(75);
  gym.timer_.toggle(millis(), 90);
  gym.render_plan();
  hidden(gym.media_empty_, true);
  // The community adapter's original geometric placeholder, not exercise media.
  for (int x : {164, 188, 300, 324}) {
    auto *plate = gym.box(gym.media_stage_, 64 + x, 110, 24, 122, 0xb8ee56);
    lv_obj_set_style_radius(plate, 6, 0);
  }
  gym.box(gym.media_stage_, 264, 166, 112, 12, 0xb8ee56);
  auto *placeholder = gym.label(gym.media_stage_, "No exercise illustration", 64, 274, 512, 24, &f16, TEXT);
  lv_obj_set_style_text_align(placeholder, LV_TEXT_ALIGN_CENTER, 0);
  snapshot(root, "workout.rgb");
  lv_display_delete(display);
  lv_deinit();
}
