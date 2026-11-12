#include "gym_native.h"
#include <cstring>

namespace esphome::gym_native {

bool GymNative::plan_fresh() const {
  return valid_ && !connection_lost_ && wifi::global_wifi_component->is_connected() &&
      millis() - last_success_ <= PLAN_FRESH_MS;
}

void GymNative::connection_failed() {
  if (!connection_lost_ && valid_) ++connection_losses_;
  connection_lost_ = true;
  plan_retry_ = true;
  // Keep the same person's last accepted plan, editor, media and timer in RAM.
  // None of this is a confirmation that an unacknowledged command was saved.
  update_status(valid_ ? OFFLINE_STATUS : "Frakoblet · prøver igjen", true);
  if (modal_message_ && !command_busy_) {
    lv_label_set_text(modal_message_, "Frakoblet · venter på forbindelse");
    modal_connection_message_ = true;
  }
}

void GymNative::connection_restored() {
  if (connection_lost_ && valid_) ++connection_recoveries_;
  connection_lost_ = false;
  plan_retry_ = false;
  if (valid_ && std::strcmp(lv_label_get_text(status_label_), OFFLINE_STATUS) == 0)
    update_status("");
  if (modal_connection_message_ && modal_message_ && !command_busy_ &&
      std::strcmp(lv_label_get_text(modal_message_), "Frakoblet · venter på forbindelse") == 0)
    lv_label_set_text(modal_message_, "");
  modal_connection_message_ = false;
}

void GymNative::check_connection() {
  if (valid_ && !connection_lost_ &&
      (!wifi::global_wifi_component->is_connected() || millis() - last_success_ > PLAN_FRESH_MS))
    connection_failed();
}

void GymNative::reset_connection() {
  connection_lost_ = true;
  plan_retry_ = true;
  modal_connection_message_ = false;
}

void GymNative::receive_plan(bool ok, int status, const std::string &body) {
  if (!ok && (status == 400 || status == 409)) {
    // A removed routine is not a transport outage. Invalidate only this preview.
    lock_request();
    wanted_routine_.clear();
    ++context_;
    unlock_request();
    clear_plan("Økten er endret · henter på nytt");
  } else if (!ok && (status == 401 || status == 403 || status == 404)) {
    // Do not retain private content after explicit loss of access/profile.
    clear_plan("Treningsdata utilgjengelige · kontroller tilgangen");
  } else if (!ok || !accept_plan(body)) {
    // Timeouts, 5xx and malformed replies must not erase a valid snapshot.
    connection_failed();
  }
}

bool GymNative::allow_submission() {
  if (plan_fresh()) return true;
  connection_failed();
  return false;  // No offline command queue and no optimistic performed sets.
}

}  // namespace esphome::gym_native
