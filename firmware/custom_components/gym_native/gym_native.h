#pragma once

#include "esphome/core/component.h"
#include "esphome/components/json/json_util.h"
#include "esphome/components/wifi/wifi_component.h"
#include "esphome/components/lvgl/lvgl_esphome.h"
// LVGL 9.5 exposes image-cache invalidation in this public instance header,
// not through the umbrella lvgl.h included by ESPHome.
#include <src/misc/cache/instance/lv_image_cache.h>
#include "esp_http_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "timer.h"
#include "media_buffer.h"
#include "media_cache.h"
#include "set_feedback.h"
#include "weight_control.h"
#include "display_policy.h"
#include "ui_style.h"
#include "workout_progress.h"
#include "ui_text.h"
#include "person_handoff.h"
#include "esphome/core/preferences.h"
#include "esphome/components/light/light_state.h"
#include "esphome/components/time/real_time_clock.h"
#include "esphome/components/web_server_base/web_server_base.h"

#include <array>
#include <atomic>
#include <string>
#include <vector>

namespace esphome::gym_native {

struct Person {
  std::string slug;
  std::string name;
};

struct RoutineChoice { std::string key, name; };

struct Exercise {
  std::string name, target, load, detail, note, image, animation;
  struct Row { std::string name, load, target; };
  std::vector<Row> rows;
  struct Result { float weight = 0, reps = 0, seconds = 0, minutes = 0, speed = 0; bool done = false; };
  struct Set { Result value, left, right; bool per_side = false, warmup = false; };
  std::vector<Set> sets;
  std::string mode, unit;
  float weight_step = 0, weight_max = 0;
  std::vector<float> weight_options;
  std::array<float, 18> muscles{};
  uint32_t rest = 0;
  unsigned work_sets = 0;
};

class GymNative : public Component, public AsyncWebHandler {
 public:
  void set_timezone(const std::string &value) { timezone_ = value; }
  void set_language(const std::string &value) { ui_.english = value == "en"; }
  void set_url(const std::string &value) { url_ = value; }
  void set_token(const std::string &value) { token_ = value; }
  void set_write_token(const std::string &value) { write_token_ = value; }
  void set_backlight(light::LightState *value) { backlight_ = value; }
  void set_clock(time::RealTimeClock *value) { clock_ = value; }
  void set_display_lvgl(lvgl::LvglComponent *value) { display_lvgl_ = value; }
  void set_admin_routes(const std::array<std::string, 8> &value) { admin_routes_ = value; }
  void configure_display(bool enabled, float start, float end, float day, float night, float wake);
  void note_touch();
  void wake_display();
  void external_display(bool on);
  void settings_saved(bool success);
  bool canHandle(AsyncWebServerRequest *request) const override;
  void handleRequest(AsyncWebServerRequest *request) override;
  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }
  void setup() override;
  void loop() override;
  void begin(const lv_font_t *small, const lv_font_t *normal,
             const lv_font_t *heading, const lv_font_t *large, const lv_font_t *exercise);
  void choose_person(int index);
  void choose_day(int day);
  void choose_exercise(int index);
  void picker(Handoff completion = Handoff::NONE);
  void toggle_animation();
  void toggle_timer();
  void adjust_timer(int delta);
  void reset_timer();
  #ifdef GYM_ACCEPTANCE
  void test_action(const std::string &action, int index);
  #endif
  std::string diagnostics() const;

 protected:
  static void worker_entry(void *context) { static_cast<GymNative *>(context)->worker(); }
  void worker();
  static void media_worker_entry(void *context) { static_cast<GymNative *>(context)->media_worker(); }
  void media_worker();
  bool media_wanted(uint32_t context, const std::string &route);
  bool get(const std::string &route, std::string &body, size_t limit,
           uint32_t context, uint32_t media = 0, MediaBuffer *binary = nullptr,
           const std::string *command = nullptr, int *status = nullptr);
  bool accept_people(const std::string &body);
  bool accept_plan(const std::string &body);
  bool plan_fresh() const;
  void receive_plan(bool ok, int status, const std::string &body);
  void connection_failed();
  void connection_restored();
  void check_connection();
  void reset_connection();
  bool allow_submission();
  bool accept_media(SharedMedia body, const std::string &route);
  bool unpack_media(MediaBuffer &body);
  void clear_plan(const char *status);
  void request_media();
  void hide_media();
  void show_frame(unsigned frame);
  void render_plan();
  void apply_display();
  void update_admin_snapshot();
  void render_exercise();
  void update_exercise_overflow();
  static void exercise_scroll(lv_event_t *event);
  void render_timer();
  void update_status(const char *text, bool error = false);
  void render_session();
  void render_muscles();
  void show_muscles();
  void apply_set_feedback();
  void session_action();
  void next_set();
  void edit_set(int encoded);
  void adjust_result(int field);
  void step_result(int field);
  void select_result_step(int encoded);
  void submit_result(bool done);
  void submit(const std::string &action, bool done = true);
  void show_finish();
  void show_pair();
  void show_routines();
  void render_rest_day();
  void choose_routine(int index);
  void close_modal();
  void update_editor();
  void show_weight_picker(int manual = 0);
  void close_weight_picker();
  void choose_weight(int index);
  void weight_key(int key);
  void use_weight();
  void lock_request();
  void unlock_request();

  lv_obj_t *label(lv_obj_t *parent, const char *text, int x, int y, int width,
                  int height, const lv_font_t *font, uint32_t color = 0xf6f7f8);
  lv_obj_t *box(lv_obj_t *parent, int x, int y, int width, int height,
                uint32_t color, bool scroll = false);
  lv_obj_t *button(lv_obj_t *parent, const char *text, int x, int y, int width,
                   int height, int action, int value = 0, bool primary = false);
  void style_button(lv_obj_t *object, bool primary);
  static void click(lv_event_t *event);
  struct Binding { GymNative *owner; int action; int value; };
  std::array<Binding, 224> bindings_{};
  unsigned binding_count_ = 0;

  std::string url_, token_, write_token_;
  SemaphoreHandle_t mutex_ = nullptr;
  TaskHandle_t task_ = nullptr, media_task_ = nullptr;
  std::atomic<uint32_t> context_{1}, media_generation_{1};
  std::string wanted_slug_, wanted_media_, wanted_prefetch_, wanted_routine_;
  std::string wanted_command_, command_action_;
  std::atomic<bool> session_active_{false};
  std::atomic<bool> plan_retry_{true};
  int wanted_day_ = -1;
  std::string pending_;
  SharedMedia pending_binary_;
  bool pending_media_ready_ = false;
  std::string pending_media_route_;
  uint32_t pending_media_context_ = 0, pending_media_generation_ = 0;
  std::atomic<bool> media_paused_{false}, prefetch_ready_{false};
  std::atomic<unsigned> prefetch_downloads_{0};
  bool media_loading_ = false;
  std::string displayed_route_, displayed_exercise_;
  MediaCache cache_;
  std::atomic<unsigned> cache_hits_{0}, media_downloads_{0};
  std::atomic<size_t> cache_bytes_{0}, last_wire_bytes_{0};
  uint32_t media_requested_at_ = 0, last_media_load_ms_ = 0;
  uint32_t pending_context_ = 0;
  int pending_kind_ = 0;
  bool pending_ok_ = false;
  int pending_status_ = 0;

  std::vector<Person> people_;
  std::vector<Exercise> exercises_;
  std::vector<RoutineChoice> routine_choices_;
  std::string selected_routine_;
  std::string title_, date_, revision_;
  std::string session_id_, session_phase_, pair_code_, result_state_;
  unsigned editing_revision_ = 0, session_revision_ = 0, session_done_ = 0, session_total_ = 0;
  double session_elapsed_ = 0;
  float session_volume_ = 0;
  std::string volume_unit_;
  MediaBuffer muscle_pixels_;
  lv_image_dsc_t muscle_descriptor_{};
  std::array<float, 18> muscle_weights_{};
  uint32_t elapsed_received_ = 0;
  bool paired_ = false, command_busy_ = false;
  Handoff pending_handoff_ = Handoff::NONE;
  int modal_kind_ = 0, editing_row_ = -1, editing_side_ = 0;
  Exercise::Result editing_value_;
  SetFeedback set_feedback_;
  SetScroll set_scroll_;
  unsigned automatic_rests_ = 0, automatic_follows_ = 0;
  SharedMedia media_bytes_;
  std::array<bool, 7> week_{};
  int person_ = -1, day_ = -1, selected_ = 0;
  bool bound_ = false, valid_ = false, playing_ = false;
  bool connection_lost_ = true, modal_connection_message_ = false;
  unsigned connection_losses_ = 0, connection_recoveries_ = 0;
  static constexpr uint32_t PLAN_FRESH_MS = 70000;
  static constexpr const char *OFFLINE_STATUS = "Frakoblet · viser sist hentede økt";
  bool session_button_primary_ = true;
  uint32_t last_success_ = 0, last_tick_ = 0, last_frame_ = 0;
  unsigned media_width_ = 0, media_height_ = 0, media_frames_ = 0, media_delay_ = 0;
  unsigned frame_ = 0, frames_shown_ = 0;
  gym_panel::Timer timer_;
  DisplayPolicy display_policy_;
  light::LightState *backlight_ = nullptr;
  time::RealTimeClock *clock_ = nullptr;
  lvgl::LvglComponent *display_lvgl_ = nullptr;
  bool display_asleep_ = false, applying_display_ = false, settings_saved_ = false;
  uint32_t last_admin_snapshot_ = 0, settings_store_sequence_ = 0;
  std::string admin_snapshot_;
  std::string timezone_{"Europe/Oslo"};
  UiText ui_;
  std::array<std::string, 8> admin_routes_{};
  lv_image_dsc_t image_descriptor_{};
  const lv_font_t *small_ = nullptr, *normal_ = nullptr, *heading_ = nullptr, *large_ = nullptr;
  const lv_font_t *exercise_font_ = nullptr;
  lv_obj_t *root_ = nullptr, *welcome_ = nullptr, *workout_ = nullptr;
  lv_obj_t *welcome_status_ = nullptr, *welcome_heading_ = nullptr;
  lv_obj_t *people_list_ = nullptr, *exercise_list_ = nullptr, *rows_ = nullptr;
  lv_obj_t *exercise_more_ = nullptr;
  lv_obj_t *brand_label_ = nullptr, *date_label_ = nullptr;
  lv_obj_t *volume_label_ = nullptr, *volume_title_ = nullptr;
  lv_obj_t *muscle_button_ = nullptr, *muscle_image_ = nullptr;
  lv_obj_t *person_button_ = nullptr;
  int image_display_width_ = 512;
  lv_obj_t *routine_label_ = nullptr, *position_label_ = nullptr;
  lv_obj_t *exercise_label_ = nullptr, *detail_label_ = nullptr, *note_label_ = nullptr;
  lv_obj_t *note_scroller_ = nullptr;
  lv_obj_t *set_count_ = nullptr, *target_label_ = nullptr, *load_label_ = nullptr;
  lv_obj_t *timer_label_ = nullptr, *timer_button_ = nullptr, *timer_text_ = nullptr;
  lv_obj_t *status_label_ = nullptr, *person_text_ = nullptr;
  lv_obj_t *media_stage_ = nullptr, *media_image_ = nullptr, *media_empty_ = nullptr;
  lv_obj_t *media_hit_area_ = nullptr, *media_viewport_ = nullptr;
  lv_obj_t *session_button_ = nullptr, *session_text_ = nullptr, *session_label_ = nullptr;
  lv_obj_t *routine_button_ = nullptr;
  lv_obj_t *rest_page_ = nullptr, *rest_list_ = nullptr, *rest_heading_ = nullptr, *rest_empty_ = nullptr;
  lv_obj_t *set_button_ = nullptr, *modal_ = nullptr, *modal_message_ = nullptr, *pair_label_ = nullptr;
  std::array<lv_obj_t *, 3> result_labels_{};
  std::array<int, 3> editing_steps_{{1, 1, 1}};
  lv_obj_t *weight_picker_ = nullptr, *weight_input_ = nullptr, *weight_apply_ = nullptr;
  lv_obj_t *weight_error_ = nullptr;
  unsigned weight_binding_start_ = 0;
  WeightEntry weight_entry_;
  std::array<std::array<lv_obj_t *, 4>, 3> step_buttons_{};
  std::array<lv_obj_t *, 7> days_{};
  std::array<lv_obj_t *, 6> controls_{};
  std::vector<lv_obj_t *> exercise_buttons_;
  std::vector<lv_obj_t *> exercise_done_labels_;
};
}  // namespace esphome::gym_native
