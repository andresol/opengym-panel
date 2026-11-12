#pragma once
#include "esphome/core/component.h"
#include "esphome/components/json/json_util.h"
#include "esphome/components/wifi/wifi_component.h"
#include "esphome/components/lvgl/lvgl_esphome.h"
#include "esp_http_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <atomic>
#include <array>
#include <vector>
#include <string>
#include "timer.h"
namespace esphome { namespace gym_panel {
struct Entry {std::string name,target,load,detail,note; uint32_t rest=0;};
class GymPanel : public Component {
 public:
  void set_url(const std::string &v){url_=v;}
  void set_token(const std::string &v){token_=v;}
  float get_setup_priority() const override {return setup_priority::AFTER_WIFI;}
  void setup() override;
  void loop() override;
  void bind(lv_obj_t *routine,lv_obj_t *position,lv_obj_t *exercise,lv_obj_t *target,lv_obj_t *load,lv_obj_t *detail,lv_obj_t *note,lv_obj_t *timer,lv_obj_t *status,lv_obj_t *date,lv_obj_t *timer_label, std::array<lv_obj_t*,7> days,std::array<lv_obj_t*,6> controls);
  void select_day(int day);
  void navigate(int delta);
  void timer_toggle();
  void timer_adjust(int delta);
  void timer_reset();
 protected:
  static void worker_entry(void *ctx){static_cast<GymPanel*>(ctx)->worker();}
  static esp_err_t http_event(esp_http_client_event_t *event);
  void worker(); void render(); void unavailable(); bool accept(const std::string &body);
  std::string url_,token_,pending_,title_,date_,revision_;
  SemaphoreHandle_t mutex_=nullptr; TaskHandle_t task_=nullptr;
  std::atomic<int> wanted_day_{-1}; std::atomic<uint32_t> generation_{1};
  bool result_ready_=false,result_ok_=false,bound_=false,valid_=false;
  uint32_t result_generation_=0,last_success_=0,last_render_=0;
  std::vector<Entry> entries_; size_t selected_=0; int day_=-1; std::array<bool,7> week_{}; Timer timer_;
  std::array<lv_obj_t*,11> labels_{}; std::array<lv_obj_t*,7> days_{}; std::array<lv_obj_t*,6> controls_{};
};
}}
