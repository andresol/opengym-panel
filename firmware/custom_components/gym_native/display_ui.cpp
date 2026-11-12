#include "gym_native.h"
#include "admin_page.h"
#include "esphome/core/defines.h"
#include <cmath>

namespace esphome::gym_native {
void GymNative::configure_display(bool enabled, float start, float end, float day, float night, float wake) {
  if (!std::isfinite(start) || !std::isfinite(end) || !std::isfinite(day) ||
      !std::isfinite(night) || !std::isfinite(wake)) return;
  display_policy_.enabled = enabled;
  display_policy_.start = std::clamp(static_cast<int>(start), 0, 1439);
  display_policy_.end = std::clamp(static_cast<int>(end), 0, 1439);
  display_policy_.day_percent = std::clamp(static_cast<int>(day), 10, 100);
  display_policy_.night_percent = std::clamp(static_cast<int>(night), 5, 50);
  display_policy_.wake_ms = std::clamp(static_cast<int>(wake), 1, 30) * 60000U;
  apply_display();
}

void GymNative::note_touch() {
  // A sleeping press is consumed by LVGL; wake only on its release/on_resume.
  if (!display_asleep_) display_policy_.wake(millis());
}

void GymNative::wake_display() {
  if (!bound_ || applying_display_) return;
  display_policy_.wake(millis());
  apply_display();
}

void GymNative::external_display(bool on) {
  if (!bound_ || applying_display_) return;
  if (on) display_policy_.wake(millis());
  else display_policy_.manual_sleep = true;
  apply_display();
}

void GymNative::settings_saved(bool success) {
  settings_saved_ = success;
  ++settings_store_sequence_;
  last_admin_snapshot_ = 0;
}

void GymNative::apply_display() {
  if (!bound_ || !backlight_ || !display_lvgl_ || !clock_ || applying_display_) return;
  auto now = clock_->now();
  const bool night = display_policy_.night(now.is_valid(), now.hour * 60 + now.minute);
  const bool sleep = display_policy_.sleep(now.is_valid(), now.hour * 60 + now.minute, millis());
  const float brightness = (night ? display_policy_.night_percent : display_policy_.day_percent) / 100.0f;
  applying_display_ = true;
  if (sleep) {
    if (!display_lvgl_->is_paused()) display_lvgl_->set_paused(true, false);
    if (backlight_->current_values.is_on()) backlight_->turn_off().perform();
  } else {
    if (!backlight_->current_values.is_on() ||
        std::fabs(backlight_->current_values.get_brightness() - brightness) > 0.005f) {
      auto call = backlight_->turn_on();
      call.set_brightness(brightness);
      call.perform();
    }
    if (display_lvgl_->is_paused()) display_lvgl_->set_paused(false, false);
  }
  const bool waking = display_asleep_ && !sleep;
  display_asleep_ = sleep;
  applying_display_ = false;
  if (waking) { render_timer(); render_session(); last_frame_ = millis(); }
}

void GymNative::update_admin_snapshot() {
  if (!clock_ || !backlight_ || millis() - last_admin_snapshot_ < 1000) return;
  last_admin_snapshot_ = millis();
  auto now = clock_->now();
  // Deliberate allowlist: no profile names, workout results, identifiers or keys.
  const auto body = json::build_json([&](JsonObject root) {
    root["version"] = ESPHOME_PROJECT_VERSION;
    root["uptimeSeconds"] = millis() / 1000;
    root["wifiConnected"] = wifi::global_wifi_component->is_connected();
    root["profiles"] = people_.size();
    root["clockValid"] = now.is_valid();
    root["localTime"] = now.is_valid() ? now.strftime("%d.%m.%Y %H:%M:%S") : "";
    root["timezone"] = timezone_;
    root["displayOn"] = backlight_->current_values.is_on();
    root["brightness"] = static_cast<int>(std::lround(backlight_->current_values.get_brightness() * 100));
    root["nightActive"] = display_policy_.night(now.is_valid(), now.hour * 60 + now.minute);
    root["nightEnabled"] = display_policy_.enabled;
    root["nightStart"] = display_policy_.start;
    root["nightEnd"] = display_policy_.end;
    root["dayBrightness"] = display_policy_.day_percent;
    root["nightBrightness"] = display_policy_.night_percent;
    root["wakeMinutes"] = display_policy_.wake_ms / 60000;
    root["idleTimeoutMinutes"] = DisplayPolicy::IDLE_TIMEOUT_MS / 60000U;
    root["idleSeconds"] = display_policy_.idle_seconds(millis());
    root["idleExpired"] = display_policy_.idle_expired;
    auto routes = root["routes"].to<JsonObject>();
    const char *keys[] = {"nightStart", "nightEnd", "dayBrightness", "nightBrightness", "wakeMinutes", "nightEnabled", "save", "light"};
    for (size_t i = 0; i < admin_routes_.size(); ++i) routes[keys[i]] = admin_routes_[i];
    root["settingsStored"] = settings_saved_;
    root["storeSequence"] = settings_store_sequence_;
    root["dataFresh"] = plan_fresh();
    root["retainedPlan"] = valid_ && !plan_fresh();
    root["dataAgeSeconds"] = valid_ ? (millis() - last_success_) / 1000 : 0;
    root["connectionLosses"] = connection_losses_;
    root["connectionRecoveries"] = connection_recoveries_;
    root["sessionActive"] = !session_id_.empty();
    root["heapFree"] = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    root["psramFree"] = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
  });
  if (body.size() > 4096) return;
  lock_request(); admin_snapshot_ = body; unlock_request();
}

bool GymNative::canHandle(AsyncWebServerRequest *request) const {
  if (request->method() != HTTP_GET) return false;
  char buffer[AsyncWebServerRequest::URL_BUF_SIZE];
  const auto url = request->url_to(buffer);
  return url == "/admin" || url == "/admin/" || url == "/admin/status" || url == "/admin/diagnostics.json";
}

void GymNative::handleRequest(AsyncWebServerRequest *request) {
  char buffer[AsyncWebServerRequest::URL_BUF_SIZE];
  const auto url = request->url_to(buffer);
  AsyncWebServerResponse *response;
  if (url == "/admin" || url == "/admin/") {
    response = request->beginResponse(200, "text/html; charset=utf-8",
        reinterpret_cast<const uint8_t *>(ADMIN_PAGE), sizeof(ADMIN_PAGE) - 1);
    response->addHeader("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'");
  } else {
    // HTTP runs on its own task. Never inspect LVGL or mutable session objects here.
    if (xSemaphoreTake(mutex_, pdMS_TO_TICKS(30)) != pdTRUE) { request->send(503); return; }
    const auto snapshot = admin_snapshot_;
    unlock_request();
    if (snapshot.empty()) { request->send(503); return; }
    response = request->beginResponse(200, "application/json; charset=utf-8", snapshot);
    if (url == "/admin/diagnostics.json")
      response->addHeader("Content-Disposition", "attachment; filename=opengym-panel-diagnostics.json");
  }
  response->addHeader("Cache-Control", "no-store");
  response->addHeader("X-Content-Type-Options", "nosniff");
  request->send(response);
}
}  // namespace esphome::gym_native
