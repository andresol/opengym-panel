"""Exercise production outage handling and workers with deterministic I/O.

Only synthetic sessions and recording UI objects. No physical device, network
interruption, server mutation or OTA is used by these tests.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'firmware/custom_components/gym_native'


class ConnectionTests(unittest.TestCase):
    def compile_run(self, source):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(source)
            subprocess.run([
                'g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-I', str(COMPONENT), str(path / 'test.cpp'), '-o', str(path / 'test'),
            ], check=True)
            subprocess.run([str(path / 'test')], check=True, timeout=10)

    def test_snapshot_editor_timer_freshness_and_hard_invalidation(self):
        production = (COMPONENT / 'connection.cpp').read_text().replace('#include "gym_native.h"', '')
        fixture = r'''
#include "ui_text.h"
esphome::gym_native::UiText ui_;
#include "timer.h"
#include <atomic>
#include <cassert>
#include <cstdint>
#include <string>
#include <vector>
uint32_t now = 1000;
uint32_t millis() {return now;}
namespace wifi {
struct WiFi {bool connected=true; bool is_connected() {return connected;}} wifi;
WiFi *global_wifi_component=&wifi;
}
struct Obj {std::string text="Unsent editor";};
void lv_label_set_text(Obj *o, const char *s) {o->text=s;}
const char *lv_label_get_text(Obj *o) {return o->text.c_str();}
namespace esphome::gym_native {
class GymNative {
 public:
  bool plan_fresh() const;
  void receive_plan(bool, int, const std::string &);
  void connection_failed(); void connection_restored(); void check_connection();
  void reset_connection(); bool allow_submission();
  void lock_request() {} void unlock_request() {}
  void update_status(const char *s, bool=false) {status=s;status_label_->text=s;}
  void clear_plan(const char *s) {
    reset_connection(); valid_=false; exercises.clear(); media.clear();
    selected=0; editor=0; timer.reset(0); ++clears; status=s;
  }
  bool accept_plan(const std::string &s) {
    ++accepted;
    if (s!="valid-alpha") return false;
    connection_restored(); valid_=true; last_success_=millis(); return true;
  }
  static constexpr uint32_t PLAN_FRESH_MS=70000;
  static constexpr const char *OFFLINE_STATUS="Frakoblet · viser sist hentede økt";
  bool valid_=true, connection_lost_=false, modal_connection_message_=false;
  bool command_busy_=false;
  std::atomic<bool> plan_retry_{false};
  unsigned connection_losses_=0, connection_recoveries_=0;
  uint32_t last_success_=1000, context_=7;
  std::string wanted_routine_="routine-alpha", status, media="image-alpha";
  std::string session_id="session-alpha", wanted_command;
  std::vector<int> exercises{1,2,3};
  unsigned selected=2, clears=0, accepted=0;
  float editor=7.3f;
  esphome::gym_panel::Timer timer;
  Obj modal, status_object; Obj *modal_message_=&modal, *status_label_=&status_object;
};
}
'''
        tests = r'''
using namespace esphome::gym_native;
int main() {
  GymNative g;
  g.timer.reset(180);g.timer.toggle(now,180);
  const auto deadline=g.timer.deadline;
  assert(g.plan_fresh());
  wifi::wifi.connected=false;
  g.check_connection();
  assert(!g.plan_fresh() && g.connection_lost_ && g.plan_retry_);
  assert(g.valid_ && g.exercises.size()==3 && g.selected==2 && g.media=="image-alpha");
  assert(g.session_id=="session-alpha" && g.editor==7.3f && g.clears==0);
  assert(g.timer.running && g.timer.deadline==deadline && g.connection_losses_==1);
  assert(g.modal_connection_message_ && !g.modal.text.empty());
  now+=5000;g.timer.tick(now);g.check_connection();
  assert(g.timer.remaining(now)==175 && g.connection_losses_==1);
  assert(!g.allow_submission() && g.wanted_command.empty());
  // Wi-Fi up is not enough: require an accepted, same-context server reply.
  wifi::wifi.connected=true;
  assert(!g.plan_fresh() && !g.allow_submission());
  for (int code : {0,408,429,500,502,503}) g.receive_plan(false,code,"");
  g.receive_plan(true,200,"malformed");
  g.receive_plan(true,200,"valid-beta"); // Wrong identity never replaces alpha.
  assert(g.valid_ && !g.plan_fresh() && g.clears==0 && g.connection_losses_==1);
  assert(g.media=="image-alpha" && g.exercises.size()==3 && g.editor==7.3f);
  g.receive_plan(true,200,"valid-alpha");
  assert(g.plan_fresh() && !g.plan_retry_ && g.connection_recoveries_==1);
  assert(g.selected==2 && g.editor==7.3f && g.timer.deadline==deadline);
  assert(g.modal.text.empty() && !g.modal_connection_message_ && g.allow_submission());
  assert(g.status.empty()); // Clear the offline header even while the editor is open.
  g.connection_failed();
  g.modal.text="Kontroller settverdiene"; // A real error is not an offline caption.
  g.status_object.text="Bekreftelse mangler";
  g.receive_plan(true,200,"valid-alpha");
  assert(g.modal.text=="Kontroller settverdiene" && g.status_object.text=="Bekreftelse mangler");
  // Age-out retains the snapshot and is latched even across millis rollover.
  now=g.last_success_+70000;assert(g.plan_fresh());
  ++now;g.check_connection();assert(!g.plan_fresh() && g.valid_ && g.clears==0);
  const auto losses=g.connection_losses_;
  for (int i=0;i<1000;++i) g.check_connection();
  assert(g.connection_losses_==losses);
  now=0xfffffff0u;g.receive_plan(true,200,"valid-alpha");
  now=0x100u;assert(g.plan_fresh());
  now=0x20000u;g.check_connection();assert(!g.plan_fresh() && g.valid_);
  now=0x10u;assert(!g.plan_fresh());
  // Do not change a pending command or manufacture server confirmation.
  GymNative busy;busy.command_busy_=true;busy.wanted_command="stable-request-id";
  busy.connection_failed();
  assert(busy.modal.text=="Unsent editor" && busy.wanted_command=="stable-request-id");
  assert(busy.exercises.size()==3 && busy.session_id=="session-alpha");
  // An explicit access/profile failure must erase retained private content.
  for (int code : {401,403,404}) {
    GymNative denied;denied.receive_plan(false,code,"");
    assert(!denied.valid_ && denied.clears==1 && denied.media.empty());
    assert(denied.exercises.empty() && !denied.allow_submission());
  }
  for (int code : {400,409}) {
    GymNative changed;changed.receive_plan(false,code,"");
    assert(changed.context_==8 && changed.wanted_routine_.empty());
    assert(!changed.valid_ && changed.clears==1);
  }
  // No last-known data at cold boot: don't invent an offline plan.
  GymNative cold;cold.valid_=false;cold.exercises.clear();cold.media.clear();
  cold.receive_plan(false,503,"");assert(!cold.valid_ && cold.exercises.empty());
}
'''
        self.compile_run(fixture + production + tests)

    def test_actual_worker_reconnect_retry_context_and_no_command_replay(self):
        source = (COMPONENT / 'gym_native.cpp').read_text()
        production = 'void GymNative::worker()' + source.split(
            'void GymNative::worker()', 1)[1].split('bool GymNative::unpack_media(', 1)[0]
        fixture = r'''
#include "ui_text.h"
esphome::gym_native::UiText ui_;
#include <atomic>
#include <cassert>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>
uint32_t now=1000;
uint32_t millis() {return now;}
int pdMS_TO_TICKS(int x) {return x;}
struct Stop {};
std::function<void()> tick;
void vTaskDelay(int) {tick();}
namespace wifi {
struct WiFi {bool connected=true; bool is_connected() {return connected;}} wifi;
WiFi *global_wifi_component=&wifi;
}
class GymNative {
 public:
  void worker();
  void lock_request() {} void unlock_request() {}
  bool get(const std::string &route,std::string &body,size_t,uint32_t,uint32_t,
           void*,const std::string *command,int *status) {
    requests.push_back(route);body="reply";*status=200;
    if(command) commands.push_back(*command);
    if(on_get) on_get();
    return result;
  }
  std::atomic<uint32_t> context_{1};
  std::atomic<bool> session_active_{false},plan_retry_{false};
  std::string wanted_slug_="alpha",wanted_routine_,wanted_command_,pending_;
  int wanted_day_=-1,pending_kind_=0,pending_status_=0;
  bool pending_ok_=false,result=true;
  uint32_t pending_context_=0;
  std::vector<std::string> requests,commands;
  std::function<void()> on_get;
};
void run(GymNative &g) {try {g.worker();} catch(const Stop &) {}}
'''
        tests = r'''
int main() {
  // Reconnect within a second forces a read, not the normal 30-second wait.
  {
    GymNative g;int turns=0;
    tick=[&] {
      ++turns;
      if(turns==1) {assert(g.requests.size()==1);g.pending_kind_=0;wifi::wifi.connected=false;}
      if(turns==2) {assert(g.requests.size()==1);wifi::wifi.connected=true;now+=10;}
      if(turns==3) {assert(g.requests.size()==2 && g.pending_kind_==2);throw Stop{};}
    };
    run(g);
  }
  // Server-only loss uses bounded retries, then restores normal idle polling.
  {
    GymNative g;int turns=0;now=1000;
    tick=[&] {
      ++turns;
      if(turns==1) {g.pending_kind_=0;g.plan_retry_=true;now=3999;}
      if(turns==2) {assert(g.requests.size()==1);now=4000;}
      if(turns==3) {assert(g.requests.size()==2);g.pending_kind_=0;g.plan_retry_=false;now=7000;}
      if(turns==4) {assert(g.requests.size()==2);now=34000;}
      if(turns==5) {assert(g.requests.size()==3);throw Stop{};}
    };
    run(g);
  }
  // A lost POST reply isn't replayed, even after recovery/repeated polling.
  {
    GymNative g;int turns=0;now=1000;
    g.wanted_command_="fixed-request";g.result=false;
    tick=[&] {
      ++turns;
      if(turns==1) {
        assert(g.pending_kind_==4 && g.wanted_command_.empty());
        g.pending_kind_=0;g.plan_retry_=true;now+=3000;
      }
      if(turns==2) {assert(g.pending_kind_==2);g.pending_kind_=0;now+=3000;}
      if(turns==3) {assert(g.commands.size()==1 && g.requests.size()==3);throw Stop{};}
    };
    run(g);
  }
  // Previous-person in-flight replies are never delivered to the new context.
  {
    GymNative g;now=1000;
    g.on_get=[&] {++g.context_;g.wanted_slug_="beta";};
    tick=[&] {assert(g.pending_kind_==0);throw Stop{};};
    run(g);
  }
}
'''
        self.compile_run(fixture + production + tests)

    def test_actual_submit_cannot_queue_any_offline_action(self):
        ui = (COMPONENT / 'workout_ui.cpp').read_text()
        production = 'void GymNative::submit(' + ui.split('void GymNative::submit(', 1)[1]
        production = production.rsplit('}  // namespace esphome::gym_native', 1)[0]
        fixture = r'''
#include "ui_text.h"
esphome::gym_native::UiText ui_;
#include "set_feedback.h"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>
uint32_t millis() {return 1000;}
uint32_t esp_random() {return 42;}
unsigned builds=0;
struct JsonField {template<class T> void operator=(const T &) {}};
struct JsonObject {JsonField operator[](const char *) {return {};}};
namespace json {
template<class F> std::string build_json(F f) {++builds;f(JsonObject{});return "synthetic-payload";}
}
void caption(std::string *o,const char *s) {if(o) *o=s;}
namespace esphome::gym_native {
struct Result {float weight=7.3f,reps=12,seconds=0,minutes=0,speed=0;bool done=false;};
struct Set {bool per_side=false;Result value,left,right;};
struct Exercise {std::string mode="reps";std::vector<Set> sets{{}};};
class GymNative {
 public:
  void submit(const std::string &,bool=true);
  bool allow_submission() {++guards;return fresh;}
  void close_modal() {++closes;}
  void update_status(const char *,bool=false) {}
  void render_session() {}
  void lock_request() {} void unlock_request() {}
  bool command_busy_=false,valid_=true,fresh=false;
  int person_=0,selected_=0,editing_row_=0,editing_side_=0,day_=3;
  unsigned editing_revision_=8,session_revision_=8,guards=0,closes=0;
  std::string pair_code_="ABCDEFGH",session_id_="session-alpha",selected_routine_="routine-alpha";
  std::string wanted_command_,command_action_,message;
  std::string *modal_message_=&message;
  std::vector<Exercise> exercises_{{}};
  Result editing_value_;
  SetFeedback set_feedback_;
};
'''
        tests = r'''
}
using namespace esphome::gym_native;
int main() {
  for (const auto &action : {"start","set","finish","discard","pair"}) {
    GymNative g;
    if (std::string(action)=="start") g.session_id_.clear();
    g.submit(action);
    assert(g.guards==1 && builds==0 && g.wanted_command_.empty());
    assert(!g.command_busy_ && !g.set_feedback_.pending && g.closes==0);
    assert(g.editing_value_.weight==7.3f && !g.editing_value_.done);
  }
  GymNative recovered;recovered.fresh=true;recovered.submit("set");
  assert(builds==1 && recovered.command_busy_ && recovered.set_feedback_.pending);
  assert(!recovered.wanted_command_.empty() && !recovered.editing_value_.done);
  recovered.submit("set");assert(builds==1); // Busy guard prevents duplicate commands.
}
'''
        self.compile_run(fixture + production + tests)

    def test_offline_guards_and_diagnostics_are_wired_into_production(self):
        core = (COMPONENT / 'gym_native.cpp').read_text()
        ui = (COMPONENT / 'workout_ui.cpp').read_text()
        submit = ui.split('void GymNative::submit(', 1)[1]
        self.assertLess(submit.index('allow_submission()'), submit.index('json::build_json'))
        self.assertIn('enabled(session_button_, plan_fresh()', ui)
        self.assertIn('enabled(set_button_, plan_fresh()', ui)
        self.assertIn('receive_plan(ok, status, body);', core)
        self.assertIn('check_connection();', core)
        self.assertNotIn('clear_plan("Frakoblet', core)
        accept = core.split('bool GymNative::accept_plan(', 1)[1].split('void GymNative::update_status(', 1)[0]
        self.assertLess(accept.index('if (!ok) return false;'), accept.index('connection_restored();'))
        self.assertLess(accept.index('if (!session_id_.empty() && session.empty()) return false;'),
                        accept.index('connection_restored();'))
        admin = (COMPONENT / 'display_ui.cpp').read_text()
        self.assertIn('root["dataFresh"] = plan_fresh();', admin)
        self.assertIn('root["retainedPlan"] = valid_ && !plan_fresh();', admin)
