#include "gym_native.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include "esp_heap_caps.h"
#include "esp_memory_utils.h"
#include "miniz.h"
#include <src/misc/lv_text.h>
#include "media_format.h"
#include "esphome/core/log.h"

namespace esphome::gym_native {
namespace {

std::string text(JsonVariantConst value, size_t limit) {
  const char *s = value.as<const char *>();
  if (!s || strlen(s) > limit) return {};
  return s;
}

void set_text(lv_obj_t *object, const std::string &value) {
  if (object && value != lv_label_get_text(object)) lv_label_set_text(object, value.c_str());
}

void hidden(lv_obj_t *object, bool value) {
  if (value) lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
  else lv_obj_remove_flag(object, LV_OBJ_FLAG_HIDDEN);
}

std::string number(JsonVariantConst value) {
  const float n = value.as<float>();
  if (!std::isfinite(n) || n < 0 || n > 10000) return {};
  char buffer[32];
  snprintf(buffer, sizeof(buffer), "%.2f", n);
  std::string result(buffer);
  while (!result.empty() && result.back() == '0') result.pop_back();
  if (!result.empty() && result.back() == '.') result.pop_back();
  for (auto &c : result) if (c == '.') c = ',';
  return result;
}

std::string media_route(const std::string &source, bool animation) {
  const std::string prefix = animation ? "/media/gif/" : "/media/img/";
  if (source.compare(0, prefix.size(), prefix) != 0) return {};
  const auto file = source.substr(prefix.size());
  if (file.empty() || file.size() > 90 || file.find("..") != std::string::npos) return {};
  for (char c : file) {
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
          (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.')) return {};
  }
  return std::string(animation ? "/packed-hq/animation/" : "/packed/still/") + file;
}
}  // namespace

void GymNative::setup() {
  mutex_ = xSemaphoreCreateMutex();
  if (!mutex_ || xTaskCreate(worker_entry, "gym_native_fetch", 8192, this, 1, &task_) != pdPASS) {
    mark_failed(); return;
  }
  if (xTaskCreate(media_worker_entry, "gym_media_fetch", 8192, this, 1, &media_task_) != pdPASS) {
    mark_failed(); return;
  }
  web_server_base::global_web_server_base->add_handler(this);
}

void GymNative::lock_request() { xSemaphoreTake(mutex_, portMAX_DELAY); }
void GymNative::unlock_request() { xSemaphoreGive(mutex_); }

bool GymNative::get(const std::string &route, std::string &body, size_t limit,
                    uint32_t context, uint32_t /* media */, MediaBuffer *binary,
                    const std::string *command, int *status) {
  const uint32_t request_started = millis();
  const std::string endpoint = url_ + route;
  esp_http_client_config_t config{};
  config.url = endpoint.c_str();
  // Conversion can wait on bounded server CPU. Media has its own worker,
  // so neither UI nor workout commands wait for these response headers.
  config.timeout_ms = command ? 35000 : limit > 64000 ? 15000 : 5000;
  config.disable_auto_redirect = true;
  config.buffer_size = 4096;
  auto client = esp_http_client_init(&config);
  if (!client) return false;
  const std::string authorization = "Bearer " + (command ? write_token_ : token_);
  esp_http_client_set_header(client, "Authorization", authorization.c_str());
  if (command) {
    esp_http_client_set_method(client, HTTP_METHOD_POST);
    esp_http_client_set_header(client, "Content-Type", "application/json");
  }
  bool ok = esp_http_client_open(client, command ? command->size() : 0) == ESP_OK;
  if (ok && command) ok = esp_http_client_write(client, command->data(), command->size()) == static_cast<int>(command->size());
  const int64_t length = ok ? esp_http_client_fetch_headers(client) : -1;
  const int code = esp_http_client_get_status_code(client);
  if (status) *status = code;
  ok = ok && length > 0 && static_cast<uint64_t>(length) <= limit &&
       (code == 200 || command);
  if (ok && binary) ok = binary->allocate(static_cast<size_t>(length));
  size_t received = 0;
  if (ok) {
    if (!binary) body.reserve(static_cast<size_t>(length));
    size_t last_yield = 0;
    char buffer[4096];
    // Bound the media payload independently of its response-header timeout.
    const uint32_t started = millis();
    while (received < static_cast<size_t>(length)) {
      if (context != context_.load() || (binary && !media_wanted(context, route)) ||
          millis() - started > (binary ? 40000u : 20000u)) { ok = false; break; }
      const int count = esp_http_client_read(client, buffer, sizeof(buffer));
      if (count <= 0 || received + count > static_cast<size_t>(length)) { ok = false; break; }
      if (binary) memcpy(binary->data() + received, buffer, count);
      else body.append(buffer, count);
      received += count;
      // Network reads already block/yield. Avoid an artificial pause after
      // every TCP fragment; keep one bounded fairness yield per 64 KiB.
      if (received - last_yield >= 65536) {
        vTaskDelay(1);
        last_yield = received;
      }
    }
    ok = ok && received == static_cast<size_t>(length);
  }
  if (!ok && binary && media_wanted(context, route))
    ESP_LOGW("gym_native", "Media transfer incomplete: %u bytes, declared %lld, %u ms",
             unsigned(received), static_cast<long long>(length), unsigned(millis() - request_started));
  esp_http_client_close(client);
  esp_http_client_cleanup(client);
  return ok;
}

void GymNative::worker() {
  uint32_t seen_context = 0, last_plan = 0;
  bool connected_since_request = false;
  for (;;) {
    const uint32_t context = context_.load();
    std::string slug, route, command, routine;
    int day;
    lock_request();
    slug = wanted_slug_; day = wanted_day_; routine = wanted_routine_;
    command = wanted_command_;
    const bool busy = pending_kind_ != 0;
    unlock_request();
    const bool connected = wifi::global_wifi_component->is_connected();
    if (!connected) connected_since_request = false;
    if (!busy && connected) {
      int kind = 0;
      if (!command.empty()) { kind = 4; route = "/api/profiles/" + slug + "/action"; }
      else if (!connected_since_request || context != seen_context ||
               millis() - last_plan >= (session_active_.load() || plan_retry_.load() ? 3000u : 30000u)) {
        kind = slug.empty() ? 1 : 2;
        route = slug.empty() ? "/api/profiles" : "/api/profiles/" + slug + "/plan";
        if (!slug.empty() && day >= 0) route += "?day=" + std::to_string(day);
        if (!slug.empty() && !routine.empty()) route += std::string(day >= 0 ? "&routine=" : "?routine=") + routine;
      }
      if (kind) {
        std::string body;
        int status = 0;
        const bool ok = get(route, body, 64000, context, 0, nullptr, kind == 4 ? &command : nullptr, &status);
        lock_request();
        if (context == context_.load()) {
          pending_ = std::move(body); pending_ok_ = ok; pending_status_ = status;
          if (kind == 4) wanted_command_.clear();
          pending_context_ = context; pending_kind_ = kind;
        }
        unlock_request();
        seen_context = context; last_plan = millis(); connected_since_request = true;
      }
    }
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

bool GymNative::unpack_media(MediaBuffer &body) {
  if (body.size() < 12) return false;
  if (memcmp(body.data(), "GYM1", 4) == 0)
    return valid_media(body.data(), body.size());
  if (memcmp(body.data(), "GYZ1", 4) != 0) return false;
  const uint32_t length = static_cast<uint32_t>(body.data()[4]) |
                          (static_cast<uint32_t>(body.data()[5]) << 8) |
                          (static_cast<uint32_t>(body.data()[6]) << 16) |
                          (static_cast<uint32_t>(body.data()[7]) << 24);
  MediaBuffer expanded;
  if (!expanded.allocate(length)) return false;
  // tinfl's ~11 KiB state cannot fit the worker's 8 KiB stack.
  auto *inflater = static_cast<tinfl_decompressor *>(
      heap_caps_calloc(1, sizeof(tinfl_decompressor), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!inflater) return false;
  tinfl_init(inflater);
  size_t input_bytes = body.size() - 8;
  size_t output_bytes = length;
  const auto result = tinfl_decompress(inflater, body.data() + 8, &input_bytes,
                                       expanded.data(), expanded.data(), &output_bytes,
                                       TINFL_FLAG_PARSE_ZLIB_HEADER |
                                       TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF);
  heap_caps_free(inflater);
  if (result != TINFL_STATUS_DONE || input_bytes != body.size() - 8 ||
      output_bytes != length || !valid_media(expanded.data(), expanded.size())) return false;
  body = std::move(expanded);
  return true;
}

lv_obj_t *GymNative::box(lv_obj_t *parent, int x, int y, int width, int height,
                         uint32_t color, bool scroll) {
  auto *object = lv_obj_create(parent);
  lv_obj_remove_style_all(object);
  lv_obj_set_pos(object, x, y);
  lv_obj_set_size(object, width, height);
  lv_obj_set_style_bg_color(object, lv_color_hex(color), 0);
  lv_obj_set_style_bg_opa(object, LV_OPA_COVER, 0);
  lv_obj_set_style_radius(object, 0, 0);
  lv_obj_set_style_pad_all(object, 0, 0);
  if (!scroll) lv_obj_remove_flag(object, LV_OBJ_FLAG_SCROLLABLE);
  else {
    lv_obj_set_scroll_dir(object, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(object, LV_SCROLLBAR_MODE_AUTO);
  }
  return object;
}

lv_obj_t *GymNative::label(lv_obj_t *parent, const char *value, int x, int y,
                           int width, int height, const lv_font_t *font, uint32_t color) {
  auto *object = lv_label_create(parent);
  lv_obj_remove_style_all(object);
  lv_obj_set_pos(object, x, y);
  lv_obj_set_size(object, width, height);
  lv_obj_set_style_text_font(object, font, 0);
  lv_obj_set_style_text_color(object, lv_color_hex(color), 0);
  lv_label_set_long_mode(object, LV_LABEL_LONG_WRAP);
  lv_label_set_text(object, value);
  return object;
}

lv_obj_t *GymNative::button(lv_obj_t *parent, const char *value, int x, int y,
                            int width, int height, int action, int argument, bool primary) {
  auto *object = lv_button_create(parent);
  lv_obj_remove_style_all(object);
  lv_obj_set_pos(object, x, y);
  lv_obj_set_size(object, width, height);
  lv_obj_set_style_bg_color(object, lv_color_hex(primary ? ACCENT : SURFACE), 0);
  lv_obj_set_style_bg_opa(object, LV_OPA_COVER, 0);
  lv_obj_set_style_radius(object, CONTROL_RADIUS, 0);
  lv_obj_set_style_bg_color(object, lv_color_hex(primary ? PRIMARY_PRESSED : SECONDARY_PRESSED), LV_STATE_PRESSED);
  lv_obj_set_style_opa(object, LV_OPA_40, LV_STATE_DISABLED);
  lv_obj_remove_flag(object, LV_OBJ_FLAG_SCROLLABLE);
  auto *caption = label(object, value, 8, 0, width - 16, height, normal_, primary ? 0x17220e : TEXT);
  lv_obj_set_style_text_align(caption, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_height(caption, LV_SIZE_CONTENT);
  lv_obj_center(caption);
  style_button(object, primary);
  // Binding storage never moves. Dynamic exercise/picker lists reuse reserved slots.
  if (binding_count_ < bindings_.size()) {
    auto *binding = &bindings_[binding_count_++];
    *binding = {this, action, argument};
    lv_obj_add_event_cb(object, click, LV_EVENT_CLICKED, binding);
  }
  return object;
}

void GymNative::style_button(lv_obj_t *object, bool primary) {
  lv_obj_set_style_bg_color(object, lv_color_hex(primary ? ACCENT : SURFACE), 0);
  lv_obj_set_style_bg_color(object, lv_color_hex(primary ? PRIMARY_PRESSED : SECONDARY_PRESSED), LV_STATE_PRESSED);
  lv_obj_set_style_text_color(lv_obj_get_child(object, 0), lv_color_hex(primary ? PRIMARY_TEXT : TEXT), 0);
}

void GymNative::click(lv_event_t *event) {
  auto *binding = static_cast<Binding *>(lv_event_get_user_data(event));
  auto *self = binding->owner;
  switch (binding->action) {
    case 1: self->choose_person(binding->value); break;
    case 2: self->picker(); break;
    case 3: self->choose_day(binding->value); break;
    case 4: self->choose_exercise(binding->value); break;
    case 5: self->choose_exercise(self->selected_ + binding->value); break;
    case 6: self->toggle_animation(); break;
    case 7: self->adjust_timer(binding->value); break;
    case 8: self->reset_timer(); break;
    case 9: self->toggle_timer(); break;
    case 10: self->session_action(); break;
    case 11: self->next_set(); break;
    case 12: self->edit_set(binding->value); break;
    case 13: self->close_modal(); break;
    case 14: self->adjust_result(binding->value); break;
    case 15: self->submit_result(true); break;
    case 16: self->submit_result(false); break;
    case 17: self->submit("finish"); break;
    case 18: self->submit("discard"); break;
    case 19: self->submit("pair"); break;
    case 20:
      if (!self->command_busy_ && self->modal_kind_ == 3 && self->pair_code_.size() < 8) {
        self->pair_code_ += static_cast<char>(binding->value);
        set_text(self->pair_label_, self->pair_code_);
      }
      break;
    case 21:
      if (!self->command_busy_ && self->modal_kind_ == 3 && !self->pair_code_.empty()) {
        self->pair_code_.pop_back();
        set_text(self->pair_label_, self->pair_code_.empty() ? "— — — — — — — —" : self->pair_code_);
      }
      break;
    case 22: self->show_routines(); break;
    case 23: self->choose_routine(binding->value); break;
    case 24: self->step_result(binding->value); break;
    case 25: self->select_result_step(binding->value); break;
    case 26: self->show_muscles(); break;
    case 27: self->show_weight_picker(binding->value); break;
    case 28: self->close_weight_picker(); break;
    case 29: self->choose_weight(binding->value); break;
    case 30: self->weight_key(binding->value); break;
    case 31: self->use_weight(); break;
  }
}

void GymNative::begin(const lv_font_t *small, const lv_font_t *normal,
                       const lv_font_t *heading, const lv_font_t *large, const lv_font_t *exercise) {
  small_ = small; normal_ = normal; heading_ = heading; large_ = large;
  exercise_font_ = exercise;
  root_ = lv_screen_active();
  lv_obj_set_style_pad_all(root_, 0, 0);
  lv_obj_set_style_bg_color(root_, lv_color_hex(BG), 0);
  lv_obj_remove_flag(root_, LV_OBJ_FLAG_SCROLLABLE);

  // Shared 24 px outer margin. Passive header values stay on the page background.
  brand_label_ = label(root_, "OpenGym", 24, 24, 244, 36, heading_);
  lv_obj_set_width(brand_label_, LV_SIZE_CONTENT);
  lv_obj_update_layout(brand_label_);
  date_label_ = label(root_, "", 24, 64, 148, 24, small_, MUTED);
  lv_obj_set_width(date_label_, lv_obj_get_width(brand_label_));
  lv_obj_set_style_text_align(date_label_, LV_TEXT_ALIGN_CENTER, 0);
  auto *person_button = button(root_, ui_.tr("Velg person", "Choose profile"), 956, 24, 300, 64, 2);
  person_button_ = person_button;
  lv_obj_set_style_border_width(person_button, 2, 0);
  lv_obj_set_style_border_color(person_button, lv_color_hex(ACCENT), 0);
  person_text_ = lv_obj_get_child(person_button, 0);
  session_label_ = label(root_, "", 24, 68, 292, 24, small_, MUTED);
  volume_title_ = label(root_, ui_.tr("VOLUM", "VOLUME"), 188, 14, 136, 24, small_, MUTED);
  volume_label_ = label(root_, "", 188, 40, 136, 24, normal_, ACCENT);
  hidden(volume_title_, true); hidden(volume_label_, true);
  welcome_ = box(root_, 0, 96, 1280, 680, BG);
  welcome_status_ = label(welcome_, handoff_caption(Handoff::NONE, ui_), 100, 52, 1080, 44, heading_, ACCENT);
  welcome_heading_ = label(welcome_, ui_.tr("Hvem skal trene?", "Who is training?"), 100, 112, 1080, 70, large_);
  people_list_ = box(welcome_, 100, 240, 1080, 344, BG, true);
  hidden(person_button_, true);
  label(people_list_, ui_.tr("Henter personer …", "Loading profiles …"), 0, 0, 1000, 50, heading_, MUTED);

  workout_ = box(root_, 0, 96, 1280, 680, BG);
  routine_label_ = label(workout_, "", 24, 12, 664, 48, normal_);
  muscle_button_ = button(workout_, "", 712, 0, 112, 64, 26);
  muscle_image_ = lv_image_create(muscle_button_);
  lv_obj_remove_flag(muscle_image_, LV_OBJ_FLAG_CLICKABLE);
  hidden(muscle_button_, true);
  for (int n = 0; n < 7; ++n) {
    const char *names[] = {ui_.tr("Man", "Mon"), ui_.tr("Tir", "Tue"), ui_.tr("Ons", "Wed"), ui_.tr("Tor", "Thu"), ui_.tr("Fre", "Fri"), ui_.tr("Lør", "Sat"), ui_.tr("Søn", "Sun")};
    days_[n] = button(workout_, names[n], 856 + n * 58, 0, 52, 48, 3, n);
    lv_obj_set_style_text_font(lv_obj_get_child(days_[n], 0), small_, 0);
  }
  label(workout_, ui_.tr("Øvelser", "Exercises"), 24, 64, 244, 24, normal_, MUTED);
  exercise_list_ = box(workout_, 24, 100, 260, 580, BG, true);
  lv_obj_add_event_cb(exercise_list_, exercise_scroll, LV_EVENT_SCROLL, this);
  exercise_more_ = label(workout_, "↓", 24, 652, 260, 24, normal_, MUTED);
  lv_obj_set_style_text_align(exercise_more_, LV_TEXT_ALIGN_CENTER, 0);
  hidden(exercise_more_, true);
  routine_button_ = button(workout_, ui_.tr("Bytt økt", "Change workout"), 24, 616, 260, 64, 22);
  hidden(routine_button_, true);
  // Inset passive text from both sides of the image column, away from controls.
  position_label_ = label(workout_, "", 316, 64, 592, 24, small_, ACCENT);
  exercise_label_ = label(workout_, "", 316, 100, 592, 72, heading_);
  media_stage_ = box(workout_, 292, 176, 640, 360, BG);
  lv_obj_set_style_radius(media_stage_, 16, 0);
  lv_obj_add_flag(media_stage_, LV_OBJ_FLAG_OVERFLOW_VISIBLE);
  media_empty_ = label(media_stage_, ui_.tr("Henter illustrasjon …", "Loading illustration …"), 24, 148, 592, 80, normal_, MUTED);
  lv_obj_set_style_text_align(media_empty_, LV_TEXT_ALIGN_CENTER, 0);
  // Match the still-image canvas exactly in BOTH modes. The animation keeps
  // its small source buffer, scaled/cropped inside this fixed pixel envelope.
  media_viewport_ = box(media_stage_, 64, 0, 512, 360, 0xffffff);
  lv_obj_remove_flag(media_viewport_, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(media_viewport_, LV_OBJ_FLAG_OVERFLOW_VISIBLE);
  hidden(media_viewport_, true);
  media_image_ = lv_image_create(media_viewport_);
  hidden(media_image_, true);
  // Image scaling changes drawn pixels, not the LVGL object's logical size.
  // Keep a transparent hit region over exactly the rendered image rectangle.
  media_hit_area_ = lv_obj_create(media_stage_);
  lv_obj_remove_style_all(media_hit_area_);
  lv_obj_set_style_bg_opa(media_hit_area_, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_width(media_hit_area_, 0, 0);
  lv_obj_set_style_outline_width(media_hit_area_, 0, 0);
  lv_obj_set_style_shadow_width(media_hit_area_, 0, 0);
  lv_obj_remove_flag(media_hit_area_, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(media_hit_area_, LV_OBJ_FLAG_CLICKABLE);
  auto *image_binding = &bindings_[binding_count_++];
  *image_binding = {this, 6, 0};
  lv_obj_add_event_cb(media_hit_area_, click, LV_EVENT_CLICKED, image_binding);
  hidden(media_hit_area_, true);
  note_scroller_ = box(workout_, 316, 548, 592, 40, BG, true);
  note_label_ = label(note_scroller_, "", 0, 0, 592, 40, small_, MUTED);
  lv_obj_set_height(note_label_, LV_SIZE_CONTENT);
  controls_[0] = button(workout_, ui_.tr("‹ Forrige", "‹ Previous"), 336, 616, 264, 64, 5, -1);
  controls_[1] = button(workout_, ui_.tr("Neste ›", "Next ›"), 624, 616, 264, 64, 5, 1);

  label(workout_, ui_.tr("ARBEIDSSETT", "WORK SETS"), 956, 64, 212, 24, small_, MUTED);
  set_count_ = label(workout_, "—", 1188, 56, 68, 52, large_, ACCENT);
  target_label_ = label(workout_, "", 956, 112, 300, 40, heading_);
  load_label_ = label(workout_, "", 956, 156, 300, 42, heading_);
  detail_label_ = label(workout_, "", 956, 208, 300, 48, small_, MUTED);
  rows_ = box(workout_, 956, 268, 300, 194, BG, true);
  timer_label_ = label(workout_, "00:00", 956, 472, 204, 54, large_);
  lv_obj_set_style_text_align(timer_label_, LV_TEXT_ALIGN_LEFT, 0);
  auto *pause_caption = label(workout_, ui_.tr("PAUSE", "REST"), 1172, 484, 84, 30, small_, MUTED);
  lv_obj_set_style_text_align(pause_caption, LV_TEXT_ALIGN_RIGHT, 0);
  controls_[2] = button(workout_, "−15 s", 956, 540, 92, 48, 7, -15);
  controls_[3] = button(workout_, "+15 s", 1164, 540, 92, 48, 7, 15);
  controls_[4] = button(workout_, ui_.tr("Nullstill", "Reset"), 1056, 540, 100, 48, 8);
  timer_button_ = button(workout_, ui_.tr("Start pause", "Start rest"), 956, 616, 300, 64, 9, 0, false);
  controls_[5] = timer_button_;
  timer_text_ = lv_obj_get_child(timer_button_, 0);
  session_button_ = button(root_, ui_.tr("Start økt", "Start workout"), 336, 24, 552, 64, 10, 0, true);
  session_text_ = lv_obj_get_child(session_button_, 0);
  hidden(session_button_, true);
  // Errors temporarily replace the left header labels, never content/navigation.
  status_label_ = label(root_, ui_.tr("Kobler til OpenGym …", "Connecting to OpenGym …"), 24, 24, 244, 64, small_, MUTED);
  set_button_ = button(root_, ui_.tr("Registrer sett", "Log set"), 624, 24, 264, 64, 11, 0, true);
  hidden(set_button_, true);
  rest_page_ = box(workout_, 0, 56, 1280, 624, BG);
  rest_heading_ = label(rest_page_, ui_.tr("Dine økter", "Your workouts"), 88, 24, 1104, 64, large_);
  rest_empty_ = label(rest_page_, ui_.tr("Ingen egne økter", "No workouts available"), 88, 110, 1104, 48, heading_, MUTED);
  rest_list_ = box(rest_page_, 88, 148, 1104, 446, BG, true);
  hidden(rest_page_, true);
  // Static controls occupy slots 0..16. Picker and exercise lists use independent ranges.
  binding_count_ = 24;
  hidden(workout_, true);
  bound_ = true;
}

bool GymNative::accept_people(const std::string &body) {
  std::vector<Person> next;
  const bool ok = json::parse_json(body, [&](JsonObject root) {
    if (!root["profiles"].is<JsonArray>()) return false;
    auto rows = root["profiles"].as<JsonArray>();
    if (rows.size() == 0 || rows.size() > 8) return false;
    for (JsonObject row : rows) {
      Person p{text(row["slug"], 31), text(row["name"], 80)};
      if (p.slug.empty() || p.name.empty()) return false;
      for (char c : p.slug) if (!(c >= 'a' && c <= 'z') && !(c >= '0' && c <= '9') && c != '-') return false;
      for (const auto &existing : next) if (existing.slug == p.slug) return false;
      next.push_back(std::move(p));
    }
    return true;
  });
  if (!ok) return false;
  const bool unchanged = next.size() == people_.size() &&
      std::equal(next.begin(), next.end(), people_.begin(), [](const Person &a, const Person &b) {
        return a.slug == b.slug && a.name == b.name;
      });
  if (unchanged) { update_status(""); return true; }
  people_ = std::move(next);
  lv_obj_clean(people_list_);
  binding_count_ = 24;
  for (size_t i = 0; i < people_.size(); ++i) {
    const auto tile = person_tile(people_.size(), i);
    auto *b = button(people_list_, people_[i].name.c_str(), tile.x, tile.y,
                     tile.width, tile.height, 1, i);
    lv_obj_set_style_radius(b, CARD_RADIUS, 0);
    lv_obj_set_style_border_width(b, 1, 0);
    lv_obj_set_style_border_color(b, lv_color_hex(RULE), 0);
    auto *name = lv_obj_get_child(b, 0);
    lv_obj_set_style_text_font(name, large_, 0);
    lv_obj_set_width(name, tile.width - 48);
    // Centre the actual single text line, not a tall, top-aligned label box.
    // Keep a bounded line for long-name ellipsis with the selected font's metrics.
    lv_obj_set_height(name, lv_font_get_line_height(large_));
    lv_label_set_long_mode(name, LV_LABEL_LONG_DOT);
    lv_obj_center(name);
  }
  update_status("");
  return true;
}

bool GymNative::accept_plan(const std::string &body) {
  if (person_ < 0 || person_ >= static_cast<int>(people_.size())) return false;
  std::vector<Exercise> next;
  std::vector<RoutineChoice> choices;
  std::string selection;
  std::string title, date, revision, session, phase, result, result_session;
  int day = -1;
  unsigned session_revision = 0, done = 0, total = 0;
  double elapsed = 0;
  float volume = 0;
  std::string volume_unit;
  bool paired = false;
  std::array<bool, 7> week{};
  const bool ok = json::parse_json(body, [&](JsonObject root) {
    if (root["schema"].as<int>() != 1 || text(root["profileSlug"], 31) != people_[person_].slug ||
        text(root["profile"], 80) != people_[person_].name || !root["entries"].is<JsonArray>() ||
        !root["week"].is<JsonArray>() || root["week"].as<JsonArray>().size() != 7) return false;
    title = text(root["title"], 640); date = text(root["date"], 10);
    revision = text(root["revision"], 32); day = root["day"].as<int>();
    if (title.empty() || date.size() != 10 || revision.empty() || day < 0 || day > 6) return false;
    paired = root["paired"].as<bool>();
    result = text(root["lastResult"]["state"], 20);
    result_session = text(root["lastResult"]["sessionId"], 64);
    if (!root["session"].isNull()) {
      session = text(root["session"]["id"], 64);
      phase = text(root["session"]["phase"], 12);
      session_revision = root["session"]["revision"].as<unsigned>();
      done = root["session"]["done"].as<unsigned>(); total = root["session"]["total"].as<unsigned>();
      volume = root["session"]["volume"].as<float>();
      volume_unit = text(root["session"]["unit"], 4);
      if (!std::isfinite(volume) || volume < 0 || volume > 1e10f ||
          (volume_unit != "kg" && volume_unit != "lb")) return false;
      elapsed = (root["serverNow"].as<double>() - root["session"]["startedAt"].as<double>()) / 1000;
      if (session.empty() || (phase != "active" && phase != "saving") || !session_revision ||
          total > 1920 || done > total || !std::isfinite(elapsed) || elapsed < 0) return false;
    } else {
      if (wanted_day_ >= 0 && day != wanted_day_) return false;
      selection = text(root["routineSelection"], 24);
      if (selection != wanted_routine_) return false;
      if (!root["routineChoices"].isNull()) {
        if (!root["routineChoices"].is<JsonArray>() || root["routineChoices"].as<JsonArray>().size() > 32) return false;
        for (JsonObject item : root["routineChoices"].as<JsonArray>()) {
          RoutineChoice choice{text(item["key"], 24), text(item["name"], 640)};
          if (choice.key.size() != 24 || choice.name.empty()) return false;
          for (char c : choice.key) if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
          for (const auto &previous : choices) if (previous.key == choice.key) return false;
          choices.push_back(std::move(choice));
        }
      }
      if (!selection.empty() && std::none_of(choices.begin(), choices.end(), [&](const RoutineChoice &c) { return c.key == selection; })) return false;
    }
    for (int i = 0; i < 7; ++i) week[i] = root["week"][i].as<bool>();
    auto entries = root["entries"].as<JsonArray>();
    if (entries.size() > 40) return false;
    for (JsonObject row : entries) {
      Exercise e;
      e.name = text(row["name"], 480); e.target = text(row["target"], 160);
      e.load = text(row["load"], 160); e.detail = text(row["detail"], 480);
      e.note = text(row["note"], 1000);
      e.image = media_route(text(row["image"], 120), false);
      e.animation = media_route(text(row["animation"], 120), true);
      const float rest = row["restSeconds"].as<float>();
      if (e.name.empty() || !std::isfinite(rest) || rest < 0 || rest > 3600 ||
          !row["sets"].is<JsonArray>() || row["sets"].as<JsonArray>().size() > 24) return false;
      e.rest = static_cast<uint32_t>(rest);
      unsigned warmup = 0, work = 0;
      e.mode = text(row["mode"], 12); e.unit = text(row["unit"], 4);
      e.weight_step = row["weightStep"].as<float>(); e.weight_max = row["weightMax"].as<float>();
      if (!std::isfinite(e.weight_step) || !std::isfinite(e.weight_max) ||
          e.weight_step < 0 || e.weight_max < 0 || e.weight_max > 2000) return false;
      if (!row["weightOptions"].isNull()) {
        if (!row["weightOptions"].is<JsonArray>() || row["weightOptions"].as<JsonArray>().size() > 24) return false;
        for (JsonVariant weight : row["weightOptions"].as<JsonArray>()) {
          if (!weight.is<float>()) return false;
          e.weight_options.push_back(weight.as<float>());
        }
        if (!valid_stack_weights(e.weight_options)) return false;
      }
      if (e.weight_step > 0 && (e.unit != "kg" || !valid_stack_weights(e.weight_options) ||
          std::abs(e.weight_max - e.weight_options.back()) > 0.001f)) return false;
      if (e.weight_step == 0 && !e.weight_options.empty()) return false;
      if (!row["muscles"].isNull()) {
        if (!row["muscles"].is<JsonArray>() || row["muscles"].as<JsonArray>().size() != 18) return false;
        for (int m = 0; m < 18; ++m) {
          e.muscles[m] = row["muscles"][m].as<float>();
          if (!std::isfinite(e.muscles[m]) || e.muscles[m] < 0 || e.muscles[m] > 1) return false;
        }
      }
      if ((e.mode != "reps" && e.mode != "time" && e.mode != "cardio") || (e.unit != "kg" && e.unit != "lb")) return false;
      const JsonArray sets = row["sets"].as<JsonArray>();
      for (JsonObject set : sets) {
        Exercise::Set stored;
        stored.warmup = set["warmup"].as<bool>();
        auto read = [](JsonVariantConst value) {
          Exercise::Result r;
          r.weight = value["weight"].as<float>(); r.reps = value["reps"].as<float>();
          r.seconds = value["seconds"].as<float>(); r.minutes = value["minutes"].as<float>();
          r.speed = value["speed"].as<float>(); r.done = value["done"].as<bool>();
          return r;
        };
        stored.value = read(set);
        stored.per_side = !set["sides"].isNull();
        if (stored.per_side) { stored.left = read(set["sides"]["L"]); stored.right = read(set["sides"]["R"]); }
        e.sets.push_back(stored);
        std::string target, load;
        if (e.mode == "time") target = ui_.decimal(number(set["seconds"])) + " s";
        else if (e.mode == "cardio") target = ui_.decimal(number(set["minutes"])) + " min";
        else {
          target = ui_.decimal(number(set["reps"])) + " reps";
          if (set["weight"].isNull()) load = ui_.tr("Valgfri vekt", "Choose weight");
          else if (row["bodyweight"].as<bool>() && set["weight"].as<float>() == 0) load = ui_.tr("Kroppsvekt", "Bodyweight");
          else load = ui_.decimal(number(set["weight"])) + " " + e.unit;
        }
        const auto caption = stored.warmup ? ui_.tr("Oppv. ", "Warm-up ") + std::to_string(++warmup) : ui_.tr("Sett ", "Set ") + std::to_string(++work);
        e.rows.push_back({caption, load, target});
      }
      e.work_sets = work;
      next.push_back(std::move(e));
    }
    return true;
  });
  if (!ok) return false;
  const auto completion = completed_handoff(session_id_, session, result, result_session, command_action_);
  if (completion != Handoff::NONE) {
    // Defer the context switch until the command/response is fully consumed.
    // Do not fetch/render the just-finished person's idle plan or illustration.
    pending_handoff_ = completion;
    return true;
  }
  // Missing/mismatched terminal confirmation must not be treated as a save.
  if (!session_id_.empty() && session.empty()) return false;
  const bool same_session = !session.empty() && session == session_id_;
  const bool changed = !valid_ || revision != revision_ || date != date_;
  const bool saved = !session_id_.empty() && session.empty() && result == "saved";
  const auto previous_image = exercises_.empty() ? std::string() : playing_ ? exercises_[selected_].animation : exercises_[selected_].image;
  connection_restored();
  valid_ = true; last_success_ = millis();
  title_ = std::move(title); date_ = std::move(date); revision_ = std::move(revision);
  day_ = day; week_ = week;
  session_id_ = std::move(session); session_phase_ = std::move(phase);
  session_revision_ = session_revision; session_done_ = done; session_total_ = total;
  session_volume_ = volume; volume_unit_ = volume_unit;
  session_elapsed_ = elapsed; elapsed_received_ = millis(); paired_ = paired;
  session_active_ = !session_id_.empty(); result_state_ = result;
  routine_choices_ = std::move(choices); selected_routine_ = std::move(selection);
  if (session_active_.load()) { lock_request(); wanted_routine_.clear(); unlock_request(); }
  if (changed) {
    exercises_ = std::move(next);
    if (!same_session) {
      selected_ = 0; playing_ = false; close_modal(); set_feedback_.cancel();
      lv_obj_scroll_to_y(rows_, 0, LV_ANIM_OFF);
      timer_.reset(exercises_.empty() ? 0 : exercises_[0].rest);
    }
    if (selected_ >= static_cast<int>(exercises_.size())) selected_ = 0;
    render_plan();
    render_muscles();
    const auto next_image = exercises_.empty() ? std::string() : playing_ ? exercises_[selected_].animation : exercises_[selected_].image;
    if (!same_session || next_image != previous_image) request_media();
  }
  if (!command_busy_ && !modal_kind_) update_status(saved ? ui_.tr("Økten er lagret i OpenGym", "Workout saved to OpenGym") : "");
  render_session();
  apply_set_feedback();
  return true;
}

void GymNative::update_status(const char *value, bool error) {
  if (valid_ && connection_lost_ && (!value[0] || !error)) {
    value = OFFLINE_STATUS;
    error = true;
  }
  set_text(status_label_, value);
  hidden(brand_label_, value[0] != '\0');
  hidden(session_label_, value[0] != '\0');
  hidden(date_label_, value[0] != '\0' || !session_id_.empty());
  lv_obj_set_style_text_color(status_label_, lv_color_hex(error ? 0xf3bb81 : MUTED), 0);
}

void GymNative::hide_media() {
  hidden(media_viewport_, true);
  hidden(media_image_, true);
  hidden(media_hit_area_, true);
  lv_image_set_src(media_image_, nullptr);
  lv_image_cache_drop(&image_descriptor_);
  image_descriptor_.data = nullptr;
  media_bytes_.reset();
  displayed_route_.clear(); displayed_exercise_.clear(); media_loading_ = false;
  media_frames_ = 0;
  hidden(media_empty_, false);
}

void GymNative::clear_plan(const char *status) {
  reset_connection();
  set_feedback_.cancel();
  valid_ = false; exercises_.clear(); render_muscles(); selected_ = 0; playing_ = false;
  routine_choices_.clear(); selected_routine_.clear();
  title_.clear(); date_.clear(); revision_.clear();
  if (!command_busy_) close_modal();
  timer_.reset(0);
  lock_request(); wanted_media_.clear(); wanted_prefetch_.clear(); prefetch_ready_ = false; ++media_generation_; unlock_request();
  hide_media();
  set_text(media_empty_, ui_.tr("Økten er utilgjengelig", "Workout unavailable"));
  render_plan();
  update_status(status, strncmp(status, ui_.tr("Frakoblet", "Disconnected"), ui_.english ? 12 : 9) == 0);
}

void GymNative::picker(Handoff completion) {
  if (command_busy_) return;
  close_modal();
  pending_handoff_ = Handoff::NONE; command_action_.clear();
  session_id_.clear(); session_phase_.clear(); session_active_ = false;
  session_revision_ = session_done_ = session_total_ = 0;
  session_elapsed_ = 0; session_volume_ = 0; volume_unit_.clear(); paired_ = false; day_ = -1; week_.fill(false);
  person_ = -1;
  lock_request(); wanted_slug_.clear(); wanted_day_ = -1; wanted_routine_.clear(); ++context_; unlock_request();
  clear_plan("");
  set_text(person_text_, ui_.tr("Velg person", "Choose profile"));
  set_text(welcome_status_, handoff_caption(completion, ui_));
  set_text(welcome_heading_, completion == Handoff::NONE ? ui_.tr("Hvem skal trene?", "Who is training?") : ui_.tr("Hvem skal trene nå?", "Who is training next?"));
  lv_obj_scroll_to_y(people_list_, 0, LV_ANIM_OFF);
  hidden(person_button_, true);
  hidden(workout_, true); hidden(welcome_, false);
}

void GymNative::choose_person(int index) {
  if (command_busy_ || index < 0 || index >= static_cast<int>(people_.size())) return;
  close_modal();
  session_id_.clear(); session_phase_.clear(); session_active_ = false;
  person_ = index;
  pending_handoff_ = Handoff::NONE; command_action_.clear();
  hidden(person_button_, false);
  lock_request(); wanted_slug_ = people_[index].slug; wanted_day_ = -1; wanted_routine_.clear(); ++context_; unlock_request();
  clear_plan(ui_.tr("Henter økt …", "Loading workout …"));
  set_text(person_text_, people_[index].name);
  hidden(welcome_, true); hidden(workout_, false);
}

void GymNative::choose_day(int day) {
  if (command_busy_ || !session_id_.empty() || person_ < 0 || day < 0 || day > 6) return;
  lock_request(); wanted_day_ = day; wanted_routine_.clear(); ++context_; unlock_request();
  clear_plan(ui_.tr("Henter økt …", "Loading workout …"));
}

void GymNative::choose_exercise(int index) {
  if (!valid_ || index < 0 || index >= static_cast<int>(exercises_.size())) return;
  selected_ = index; playing_ = false;
  set_feedback_.cancel();
  set_scroll_.reset();
  lv_obj_scroll_to_y(rows_, 0, LV_ANIM_OFF);
  // Rest belongs to the last registered set, not the exercise being previewed.
  // Keep its absolute deadline while running; only idle/expired timers adopt
  // the newly selected exercise's preset. Explicit Reset still uses that preset.
  if (!timer_.running || timer_.remaining(millis()) == 0)
    timer_.reset(exercises_[index].rest);
  render_exercise(); request_media();
  if (index < static_cast<int>(exercise_buttons_.size()))
    lv_obj_scroll_to_view(exercise_buttons_[index], LV_ANIM_OFF);
}

void GymNative::request_media() {
  media_requested_at_ = millis();
  std::string route;
  if (valid_ && !exercises_.empty()) route = playing_ ? exercises_[selected_].animation : exercises_[selected_].image;
  // Keep the same exercise visible while its animation is being fetched. Never
  // retain an illustration belonging to a different exercise/profile.
  if (exercises_.empty() || displayed_exercise_ != exercises_[selected_].image) hide_media();
  media_loading_ = !route.empty() && route != displayed_route_;
  lock_request(); wanted_media_ = route;
  wanted_prefetch_ = valid_ && !exercises_.empty() ? (playing_ ? exercises_[selected_].image : exercises_[selected_].animation) : "";
  prefetch_ready_ = false; ++media_generation_; unlock_request();
  set_text(media_empty_, exercises_.empty() ? ui_.tr("Ingen planlagt styrkeøkt", "No strength workout planned") :
           route.empty() ? ui_.tr("Ingen illustrasjon for denne øvelsen", "No illustration for this exercise") : ui_.tr("Henter illustrasjon …", "Loading illustration …"));
}

bool GymNative::accept_media(SharedMedia body, const std::string &route) {
  if (!body || body->size() < 12 || memcmp(body->data(), "GYM1", 4) != 0 || !valid_) return false;
  auto word = [&](unsigned offset) {
    return static_cast<unsigned>(body->data()[offset]) |
           (static_cast<unsigned>(body->data()[offset + 1]) << 8);
  };
  const auto w = word(4), h = word(6), frames = word(8), delay = word(10);
  if ((!playing_ && (w != 512 || h != 360 || frames != 1)) ||
      (playing_ && (w != 512 || h != 360 || frames < 1 || frames > 24 || delay < 100 || delay > 20000)) ||
      body->size() != 12 + static_cast<size_t>(w) * h * frames * 2) return false;
  hide_media();
  media_bytes_ = std::move(body);
  displayed_route_ = route; displayed_exercise_ = exercises_[selected_].image; media_loading_ = false;
  last_media_load_ms_ = millis() - media_requested_at_;
  media_width_ = w; media_height_ = h; media_frames_ = frames; media_delay_ = delay;
  frame_ = 0; last_frame_ = millis();
  image_descriptor_ = {};
  image_descriptor_.header.magic = LV_IMAGE_HEADER_MAGIC;
  image_descriptor_.header.cf = LV_COLOR_FORMAT_RGB565;
  image_descriptor_.header.w = w; image_descriptor_.header.h = h;
  image_descriptor_.header.stride = w * 2;
  image_descriptor_.data_size = w * h * 2;
  show_frame(0);
  // Both modes arrive at display resolution with identical canvas/margins.
  // Never enlarge a smaller animation or change the touch/layout geometry.
  lv_image_set_scale(media_image_, 256);
  lv_obj_center(media_image_);
  hidden(media_empty_, true); hidden(media_viewport_, false); hidden(media_image_, false);
  const int rendered_width = 512, rendered_height = 360;
  image_display_width_ = rendered_width;
  render_session();
  lv_obj_set_size(media_hit_area_, rendered_width, rendered_height);
  lv_obj_center(media_hit_area_);
  hidden(media_hit_area_, exercises_.empty() || exercises_[selected_].animation.empty());
  lv_obj_move_foreground(media_hit_area_);
  return true;
}

void GymNative::show_frame(unsigned frame) {
  lv_image_cache_drop(&image_descriptor_);
  image_descriptor_.data = reinterpret_cast<const uint8_t *>(media_bytes_->data() + 12) +
                           static_cast<size_t>(frame) * media_width_ * media_height_ * 2;
  lv_image_set_src(media_image_, &image_descriptor_);
  lv_obj_invalidate(media_image_);
  ++frames_shown_;
}

void GymNative::toggle_animation() {
  if (!valid_ || exercises_.empty() || exercises_[selected_].animation.empty()) return;
  playing_ = !playing_; request_media();
}

void GymNative::toggle_timer() {
  if (!valid_ || exercises_.empty()) return;
  timer_.toggle(millis(), exercises_[selected_].rest); render_timer();
}

void GymNative::adjust_timer(int delta) {
  if (!valid_ || exercises_.empty()) return;
  timer_.adjust(delta, millis()); render_timer();
}

void GymNative::reset_timer() {
  timer_.reset(valid_ && !exercises_.empty() ? exercises_[selected_].rest : 0);
  render_timer();
}

void GymNative::render_timer() {
  const auto remaining = timer_.remaining(millis());
  char buffer[16];
  snprintf(buffer, sizeof(buffer), "%02u:%02u", unsigned(remaining / 60), unsigned(remaining % 60));
  set_text(timer_label_, buffer);
  lv_obj_set_style_text_color(timer_label_, lv_color_hex(timer_.running && remaining ? ACCENT : TEXT), 0);
  set_text(timer_text_, timer_.running ? ui_.tr("Stopp pause", "Stop rest") : remaining ? ui_.tr("Start pause", "Start rest") : ui_.tr("Start på nytt", "Restart"));
}

void GymNative::render_plan() {
  if (!bound_) return;
  const std::string display_date = valid_
      ? date_.substr(8, 2) + "." + date_.substr(5, 2) + "." + date_.substr(0, 4)
      : "";
  set_text(date_label_, display_date);
  set_text(routine_label_, valid_ ? title_ : ui_.tr("OpenGym utilgjengelig", "OpenGym unavailable"));
  const bool can_change = valid_ && !selected_routine_.empty() && session_id_.empty();
  hidden(routine_button_, !can_change);
  const int available_height = can_change ? 500 : 580;
  const int content_height = exercises_.empty() ? 0 : (exercises_.size() - 1) * 85 + 70;
  // Reserve a plain-text footer only for overflowing lists. It never overlays a
  // tile, and stays reserved at the bottom to avoid moving tiles during a swipe.
  const int list_height = available_height - (content_height > available_height ? 36 : 0);
  const int previous_scroll = lv_obj_get_scroll_y(exercise_list_);
  hidden(exercise_more_, true);
  lv_obj_set_height(exercise_list_, list_height);
  lv_obj_set_y(exercise_more_, 100 + available_height - 28);
  lv_obj_clean(exercise_list_);
  exercise_buttons_.clear(); exercise_done_labels_.clear();
  binding_count_ = 40;
  for (size_t i = 0; i < exercises_.size(); ++i) {
    auto *b = button(exercise_list_, exercises_[i].name.c_str(), 0, i * 85, 260, 70, 4, i);
    auto *caption = lv_obj_get_child(b, 0);
    lv_obj_set_style_text_align(caption, LV_TEXT_ALIGN_LEFT, 0);
    lv_obj_set_style_text_font(caption, exercise_font_, 0);
    lv_obj_set_width(caption, 228);
    lv_obj_set_style_text_line_space(caption, 1, 0);
    lv_label_set_long_mode(caption, LV_LABEL_LONG_WRAP);
    lv_obj_align(caption, LV_ALIGN_LEFT_MID, 16, 0);
    exercise_buttons_.push_back(b);
    auto *done = label(b, "✓", 220, 23, 24, 24, normal_, ACCENT);
    lv_obj_set_style_text_align(done, LV_TEXT_ALIGN_CENTER, 0);
    hidden(done, true); exercise_done_labels_.push_back(done);
  }
  for (int i = 0; i < 7; ++i) {
    const bool active = valid_ && day_ == i;
    lv_obj_set_style_bg_color(days_[i], lv_color_hex(active ? ACCENT : BG), 0);
    lv_obj_set_style_text_color(lv_obj_get_child(days_[i], 0), lv_color_hex(active ? 0x17220e : (week_[i] ? TEXT : MUTED)), 0);
  }
  render_exercise();
  render_rest_day();
  render_session();
  lv_obj_update_layout(exercise_list_);
  lv_obj_scroll_to_y(exercise_list_, std::min(std::max(0, content_height - list_height),
                                            std::max(0, previous_scroll)), LV_ANIM_OFF);
  update_exercise_overflow();
}

void GymNative::exercise_scroll(lv_event_t *event) {
  auto *self = static_cast<GymNative *>(lv_event_get_user_data(event));
  self->update_exercise_overflow();
}

void GymNative::update_exercise_overflow() {
  if (!exercise_more_) return;
  hidden(exercise_more_, !valid_ || exercise_buttons_.empty() ||
                          lv_obj_get_scroll_bottom(exercise_list_) <= 0);
}

void GymNative::render_exercise() {
  const Exercise *e = valid_ && !exercises_.empty() ? &exercises_[selected_] : nullptr;
  set_text(position_label_, e ? ui_.tr("ØVELSE ", "EXERCISE ") + std::to_string(selected_ + 1) + ui_.tr(" AV ", " OF ") + std::to_string(exercises_.size()) : "");
  set_text(exercise_label_, e ? e->name : valid_ ? ui_.tr("Tid til å hente seg inn", "Time to recover") : ui_.tr("Ingen ferske treningsdata", "No current workout data"));
  set_text(set_count_, e ? std::to_string(e->work_sets) : "—");
  const auto target = e ? ui_.decimal(e->target) : "";
  const auto load = e ? ui_.decimal(e->load) : "";
  const auto summary = target + (target.empty() || load.empty() ? "" : " · ") + load;
  lv_point_t summary_size{};
  lv_text_get_size(&summary_size, summary.c_str(), heading_, 0, 0, 300, LV_TEXT_FLAG_EXPAND);
  const bool compact = e && !summary.empty() && summary_size.x <= 300 && summary_size.y <= 42;
  set_text(target_label_, compact ? summary : target);
  set_text(load_label_, load);
  hidden(load_label_, compact || load.empty());
  // Keep the pause/footer fixed. Reuse the released row for four full active
  // rows (4×54 + 3×8 = 240), not a large empty gap under the compact summary.
  lv_obj_set_y(detail_label_, compact ? 164 : 208);
  lv_obj_set_y(rows_, compact ? 222 : 268);
  lv_obj_set_height(rows_, compact ? 240 : 194);
  set_text(detail_label_, e ? ui_.decimal(e->detail) : "");
  set_text(note_label_, e ? e->note : "");
  lv_obj_scroll_to_y(note_scroller_, 0, LV_ANIM_OFF);
  const int previous_scroll = lv_obj_get_scroll_y(rows_);
  lv_obj_clean(rows_);
  binding_count_ = 80;
  int row_y = 0;
  // Keep the approved equal tracks and ordinary left alignment. Centre each
  // measured label vertically, including two-line values, within its own row.
  const auto columns = [&](lv_obj_t *parent, int y, const std::string &name,
                           const std::string &load, const std::string &target,
                           bool interactive, bool done, bool is_next) {
    const int row_height = interactive ? 54 : 38;
    auto *name_cell = label(parent, name.c_str(), 10, y, 90, row_height, small_);
    auto *load_cell = label(parent, load.c_str(), 102, y, 90, row_height, small_);
    auto *target_cell = label(parent, target.c_str(), 194, y, 90, row_height, small_);
    for (auto *cell : {name_cell, load_cell, target_cell}) {
      lv_obj_set_style_text_color(cell, lv_color_hex(is_next ? PRIMARY_TEXT : TEXT), 0);
      lv_obj_set_style_text_align(cell, LV_TEXT_ALIGN_LEFT, 0);
      lv_obj_set_height(cell, LV_SIZE_CONTENT);
      lv_obj_update_layout(cell);
      const int height = std::min(row_height, static_cast<int>(lv_obj_get_height(cell)));
      lv_obj_set_height(cell, height);
      lv_obj_set_y(cell, y + (row_height - height) / 2);
    }
    if (done || is_next) {
      auto *done_cell = label(parent, is_next ? ui_.tr("NESTE", "NEXT") : "✓", 10, y, 90, 24,
                              is_next ? small_ : normal_, is_next ? PRIMARY_TEXT : ACCENT);
      lv_obj_set_style_text_align(done_cell, LV_TEXT_ALIGN_LEFT, 0);
      lv_obj_set_height(done_cell, LV_SIZE_CONTENT);
      lv_obj_update_layout(done_cell);
      const int name_height = lv_obj_get_height(name_cell);
      const int done_height = lv_obj_get_height(done_cell);
      const int group_top = y + (row_height - name_height - 2 - done_height) / 2;
      lv_obj_set_y(name_cell, group_top);
      lv_obj_set_y(done_cell, group_top + name_height + 2);
    }
  };
  // Dividers belong to the scrolling rows, never to the empty viewport. There
  // is no outer border, no vertical rule and no line before/after the list.
  const auto divide_before = [&](bool interactive) {
    if (row_y == 0) return;
    auto *line = box(rows_, 8, row_y - (interactive ? 4 : 0), 276, 1, 0x343a40);
    lv_obj_remove_flag(line, LV_OBJ_FLAG_CLICKABLE);
  };
  if (e) for (size_t i = 0; i < e->rows.size(); ++i) {
    const auto &row = e->sets[i];
    const auto progress = workout_progress(e->sets);
    if (!session_id_.empty()) {
      for (int side = row.per_side ? 1 : 0; side <= (row.per_side ? 2 : 0); ++side) {
        const auto &value = side == 1 ? row.left : side == 2 ? row.right : row.value;
        char load[48] = {}, target[48] = {};
        if (e->mode == "reps") {
          snprintf(load, sizeof(load), "%s", ui_.decimal(weight_caption(value.weight, e->unit)).c_str());
          snprintf(target, sizeof(target), "%.0f reps", value.reps);
        } else snprintf(target, sizeof(target), "%s", ui_.decimal(weight_caption(
            e->mode == "time" ? value.seconds : value.minutes, e->mode == "time" ? "s" : "min")).c_str());
        divide_before(true);
        const bool is_next = progress.next_row == static_cast<int>(i) && progress.next_side == side;
        auto *b = button(rows_, "", 0, row_y, 292, 54, 12, i * 3 + side, is_next);
        hidden(lv_obj_get_child(b, 0), true);
        columns(b, 0, e->rows[i].name + (side == 1 ? ui_.tr(" V", " L") : side == 2 ? ui_.tr(" H", " R") : ""), load, target,
                true, value.done, is_next);
        lv_obj_set_style_bg_color(b, lv_color_hex(is_next ? ACCENT : value.done ? SELECTED : SURFACE), 0);
        row_y += 62;
      }
    } else {
      divide_before(false);
      columns(rows_, row_y, e->rows[i].name, e->rows[i].load, e->rows[i].target, false, false, false);
      row_y += 38;
    }
  }
  lv_obj_update_layout(rows_);
  const int content_height = std::max(0, row_y - (!session_id_.empty() ? 8 : 0));
  const int viewport_height = static_cast<int>(lv_obj_get_style_height(rows_, LV_PART_MAIN));
  const int maximum_scroll = std::max(0, content_height - viewport_height);
  const int followed_scroll = e ? set_scroll_.observe(session_id_, selected_, e->sets,
                                                     viewport_height, previous_scroll) : previous_scroll;
  lv_obj_scroll_to_y(rows_, std::min(maximum_scroll, std::max(0, followed_scroll)), LV_ANIM_OFF);
  for (size_t i = 0; i < exercise_buttons_.size(); ++i) {
    auto *b = exercise_buttons_[i];
    const bool selected = i == static_cast<size_t>(selected_);
    const bool complete = !session_id_.empty() && workout_progress(exercises_[i].sets).complete();
    hidden(exercise_done_labels_[i], !complete);
    auto *name = lv_obj_get_child(b, 0);
    lv_obj_set_width(name, complete ? 188 : 228);
    lv_obj_set_height(name, complete ? 46 : LV_SIZE_CONTENT);
    lv_label_set_long_mode(name, complete ? LV_LABEL_LONG_DOT : LV_LABEL_LONG_WRAP);
    lv_obj_align(name, LV_ALIGN_LEFT_MID, 16, 0);
    lv_obj_set_style_bg_color(b, lv_color_hex(selected ? SELECTED : SURFACE), 0);
    lv_obj_set_style_border_width(b, selected ? 2 : 1, 0);
    lv_obj_set_style_border_color(b, lv_color_hex(selected ? ACCENT : RULE), 0);
  }
  for (size_t i = 0; i < controls_.size(); ++i) {
    const bool disabled = !e || (i == 0 && selected_ == 0) || (i == 1 && selected_ + 1 >= static_cast<int>(exercises_.size()));
    if (disabled) lv_obj_add_state(controls_[i], LV_STATE_DISABLED);
    else lv_obj_remove_state(controls_[i], LV_STATE_DISABLED);
  }
  render_timer();
}

void GymNative::loop() {
  if (!bound_) return;
  apply_display();
  update_admin_snapshot();
  if (xSemaphoreTake(mutex_, 0) == pdTRUE) {
    const int kind = pending_kind_;
    const bool ok = pending_ok_;
    const int status = pending_status_;
    const auto context = pending_context_;
    std::string body = std::move(pending_);
    pending_kind_ = 0;
    unlock_request();
    if (kind && context == context_.load()) {
      if (kind == 1) {
        const bool accepted = ok && accept_people(body);
        plan_retry_ = !accepted;
        if (!accepted) update_status(ui_.tr("Personer utilgjengelige · prøver igjen", "Profiles unavailable · retrying"), true);
      } else if (kind == 2) {
        receive_plan(ok, status, body);
      } else if (kind == 4) {
        command_busy_ = false;
        if (ok && status == 200 && accept_plan(body)) {
          close_modal();
          update_status(command_action_ == "pair" ? ui_.tr("Tilkoblet OpenGym", "Connected to OpenGym") : session_id_.empty() ? result_state_ == "saved" ? ui_.tr("Økten er lagret i OpenGym", "Workout saved to OpenGym") : ui_.tr("Økten er avsluttet", "Workout finished") : "");
        } else {
          if (!ok || status == 200 || status >= 500) connection_failed();
          if (status > 0 && status != 200) set_feedback_.cancel();
          std::string error;
          if (ok) json::parse_json(body, [&](JsonObject root) { error = text(root["error"], 60); return true; });
          const char *message = ui_.tr("Bekreftelse mangler · henter økten på nytt", "Not confirmed · refreshing workout");
          if (error == "pair_required") { paired_ = false; message = ui_.tr("Koble til OpenGym for å fortsette", "Pair with OpenGym to continue"); }
          else if (error == "wrong_profile") message = ui_.tr("Koden tilhører en annen person", "This code belongs to another profile");
          else if (error == "invalid_pair_code") message = ui_.tr("Ugyldig eller utløpt kode", "Invalid or expired code");
          else if (error == "session_changed") message = ui_.tr("Økten er oppdatert · prøv igjen", "Workout updated · try again");
          else if (error == "unsupported_workout") message = ui_.tr("Denne økten må registreres i OpenGym-appen", "Log this workout in the OpenGym app");
          else if (error == "enter_result") message = ui_.tr("Registrer faktisk antall eller varighet", "Enter the actual reps or duration");
          else if (error == "invalid_value") message = ui_.tr("Kontroller settverdiene", "Check the set values");
          else if (error == "routine_unavailable" || error == "not_rest_day") message = ui_.tr("Økten er endret · velg på nytt", "Workout changed · choose again");
          update_status(message, true);
          if (modal_message_) set_text(modal_message_, message);
          if (error == "pair_required") show_pair();
          else if (error == "session_changed") close_modal();
          lock_request(); ++context_; unlock_request();
        }
        render_session();
      }
    }
  }
  if (!command_busy_ && pending_handoff_ != Handoff::NONE) {
    const auto completion = pending_handoff_;
    picker(completion);  // Cancels old profile/media context and resets only local UI state.
  }
  lock_request();
  const bool media_ready = pending_media_ready_;
  auto binary = media_ready ? std::move(pending_binary_) : SharedMedia{};
  const auto route = pending_media_route_;
  const auto media_context = pending_media_context_, generation = pending_media_generation_;
  if (media_ready) pending_media_ready_ = false;
  unlock_request();
  if (media_ready && media_context == context_.load() && generation == media_generation_.load()) {
    if (!accept_media(std::move(binary), route)) {
      media_loading_ = false;
      if (playing_) { playing_ = false; request_media(); }
      else if (!media_bytes_) set_text(media_empty_, ui_.tr("Illustrasjonen er utilgjengelig", "Illustration unavailable"));
    }
  }
  media_paused_ = display_asleep_;
  check_connection();
  if (millis() - last_tick_ >= 200) {
    timer_.tick(millis()); render_timer(); render_session(); last_tick_ = millis();
  }
  if (playing_ && !display_asleep_ && media_frames_ > 1 && millis() - last_frame_ >= media_delay_) {
    frame_ = (frame_ + 1) % media_frames_; show_frame(frame_); last_frame_ = millis();
  }
}

#ifdef GYM_ACCEPTANCE
void GymNative::test_action(const std::string &action, int index) {
  if (action == "person") choose_person(index);
  else if (action == "day") choose_day(index);
  else if (action == "exercise") choose_exercise(index);
  else if (action == "picker") picker();
  else if (action == "animation") lv_obj_send_event(media_hit_area_, LV_EVENT_CLICKED, nullptr);
  else if (action == "timer") lv_obj_send_event(timer_button_, LV_EVENT_CLICKED, nullptr);
  else if (action == "reset") reset_timer();
}
#endif

std::string GymNative::diagnostics() const {
  return json::build_json([&](JsonObject root) {
    root["version"] = ESPHOME_PROJECT_VERSION; root["valid"] = valid_;
    root["dataFresh"] = plan_fresh();
    root["retainedPlan"] = valid_ && !plan_fresh();
    root["connectionLosses"] = connection_losses_;
    root["connectionRecoveries"] = connection_recoveries_;
    root["displayAsleep"] = display_asleep_;
    root["restPage"] = rest_page_ && !lv_obj_has_flag(rest_page_, LV_OBJ_FLAG_HIDDEN);
    root["routineChoices"] = routine_choices_.size();
    root["people"] = people_.size(); root["person"] = person_;
    root["day"] = day_; root["exercises"] = exercises_.size(); root["selected"] = selected_;
    root["rows"] = valid_ && !exercises_.empty() ? exercises_[selected_].rows.size() : 0;
    root["imageFrames"] = media_frames_; root["framesShown"] = frames_shown_;
    root["playing"] = playing_; root["timerRunning"] = timer_.running;
    root["automaticRests"] = automatic_rests_; root["automaticFollows"] = automatic_follows_;
    root["setFeedbackPending"] = set_feedback_.pending;
    root["remaining"] = timer_.remaining(millis());
    root["sessionActive"] = !session_id_.empty();
    root["sessionPhase"] = session_phase_; root["setsDone"] = session_done_; root["setsTotal"] = session_total_;
    if (valid_ && !exercises_.empty()) {
      const auto progress = workout_progress(exercises_[selected_].sets);
      root["nextSetRow"] = progress.next_row; root["nextSetSide"] = progress.next_side;
      unsigned complete = 0;
      for (const auto &exercise : exercises_) if (workout_progress(exercise.sets).complete()) ++complete;
      root["completedExercises"] = complete;
    }
    root["paired"] = paired_; root["commandBusy"] = command_busy_; root["modal"] = modal_kind_;
    root["dataAgeMs"] = valid_ ? millis() - last_success_ : 0;
    root["heap"] = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    root["psram"] = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    root["mediaBytes"] = media_bytes_ ? media_bytes_->size() : 0;
    root["cacheBytes"] = cache_bytes_.load();
    root["cacheHits"] = cache_hits_.load();
    root["mediaDownloads"] = media_downloads_.load();
    root["prefetchDownloads"] = prefetch_downloads_.load();
    root["prefetchReady"] = prefetch_ready_.load();
    root["mediaLoading"] = media_loading_;
    root["lastWireBytes"] = last_wire_bytes_.load();
    root["mediaLoadMs"] = last_media_load_ms_;
    root["imageExternal"] = media_bytes_ && esp_ptr_external_ram(media_bytes_->data());
    if (bound_) {
      root["setsScrollY"] = lv_obj_get_scroll_y(rows_);
      root["imageLeft"] = lv_obj_get_style_x(media_stage_, LV_PART_MAIN) +
          (lv_obj_get_style_width(media_stage_, LV_PART_MAIN) - image_display_width_) / 2;
      root["imageWidth"] = image_display_width_;
      root["startLeft"] = lv_obj_get_style_x(session_button_, LV_PART_MAIN);
      root["startWidth"] = lv_obj_get_style_width(session_button_, LV_PART_MAIN);
      root["registerLeft"] = lv_obj_get_style_x(set_button_, LV_PART_MAIN);
      root["registerWidth"] = lv_obj_get_style_width(set_button_, LV_PART_MAIN);
      root["previousLeft"] = lv_obj_get_style_x(controls_[0], LV_PART_MAIN);
      root["previousWidth"] = lv_obj_get_style_width(controls_[0], LV_PART_MAIN);
      root["nextLeft"] = lv_obj_get_style_x(controls_[1], LV_PART_MAIN);
      root["nextWidth"] = lv_obj_get_style_width(controls_[1], LV_PART_MAIN);
      root["brandWidth"] = lv_obj_get_width(brand_label_);
      root["dateWidth"] = lv_obj_get_style_width(date_label_, LV_PART_MAIN);
      root["dateCentered"] = lv_obj_get_style_text_align(date_label_, LV_PART_MAIN) == LV_TEXT_ALIGN_CENTER;
      root["exerciseListWidth"] = lv_obj_get_style_width(exercise_list_, LV_PART_MAIN);
      root["titleLeft"] = lv_obj_get_style_x(exercise_label_, LV_PART_MAIN);
      root["titleWidth"] = lv_obj_get_style_width(exercise_label_, LV_PART_MAIN);
      root["noteLeft"] = lv_obj_get_style_x(note_scroller_, LV_PART_MAIN);
      root["noteWidth"] = lv_obj_get_style_width(note_scroller_, LV_PART_MAIN);
      root["routineTop"] = lv_obj_get_style_y(workout_, LV_PART_MAIN) + lv_obj_get_style_y(routine_label_, LV_PART_MAIN);
      root["personWidth"] = lv_obj_get_style_width(person_button_, LV_PART_MAIN);
      root["personHeight"] = lv_obj_get_style_height(person_button_, LV_PART_MAIN);
      root["pauseWidth"] = lv_obj_get_style_width(timer_button_, LV_PART_MAIN);
      root["pauseHeight"] = lv_obj_get_style_height(timer_button_, LV_PART_MAIN);
      root["navigationGap"] = lv_obj_get_style_x(controls_[1], LV_PART_MAIN) -
          (lv_obj_get_style_x(controls_[0], LV_PART_MAIN) + lv_obj_get_style_width(controls_[0], LV_PART_MAIN));
      root["imageTapBackgroundOpacity"] = lv_obj_get_style_bg_opa(media_hit_area_, LV_PART_MAIN);
      root["imageTapVisible"] = !lv_obj_has_flag(media_hit_area_, LV_OBJ_FLAG_HIDDEN);
      root["imageTapWidth"] = lv_obj_get_width(media_hit_area_);
      root["imageTapHeight"] = lv_obj_get_height(media_hit_area_);
      root["exerciseText"] = lv_label_get_text(exercise_label_);
      root["loadText"] = lv_label_get_text(load_label_);
      root["summaryText"] = lv_label_get_text(target_label_);
      root["summaryCompact"] = lv_obj_has_flag(load_label_, LV_OBJ_FLAG_HIDDEN);
      root["rowsTop"] = lv_obj_get_style_y(rows_, LV_PART_MAIN);
      root["rowsHeight"] = lv_obj_get_style_height(rows_, LV_PART_MAIN);
      root["mediaViewportWidth"] = lv_obj_get_width(media_viewport_);
      root["mediaViewportHeight"] = lv_obj_get_height(media_viewport_);
      root["status"] = lv_label_get_text(status_label_);
      root["width"] = lv_obj_get_width(root_); root["height"] = lv_obj_get_height(root_);
    }
  });
}
}  // namespace esphome::gym_native
