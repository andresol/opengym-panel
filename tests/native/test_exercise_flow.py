"""Execute production acknowledgement/navigation and primary-action methods.

Synthetic data only. Recording LVGL calls are not physical display acceptance;
the separate desktop LVGL check verifies actual scroll bounds and the indicator.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'firmware/custom_components/gym_native'


def method(source, name, following):
    return source[source.index('void GymNative::' + name):
                  source.index('void GymNative::' + following)]


class ExerciseFlowTests(unittest.TestCase):
    def test_confirmed_auto_next_rest_and_primary_finish(self):
        cpp = (COMPONENT / 'gym_native.cpp').read_text()
        ui = (COMPONENT / 'workout_ui.cpp').read_text()
        production = method(cpp, 'choose_exercise(', 'request_media(')
        production += method(ui, 'apply_set_feedback(', 'submit(')
        production += method(ui, 'render_session(', 'session_action(')
        production += method(ui, 'session_action(', 'render_rest_day(')
        fixture = r'''
#include "workout_progress.h"
#include "set_feedback.h"
#include "timer.h"
#include "weight_control.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
using namespace esphome::gym_native;
uint32_t now = 1000;
uint32_t millis() { return now; }
constexpr int LV_ANIM_OFF = 0, LV_PART_MAIN = 0;
struct Obj {
  int x=0, width=300, height=240, scroll=0, visits=0;
  bool shown=true, enabled=true, primary=false;
  std::string text;
  Obj *child=nullptr;
};
using lv_obj_t = Obj;
void lv_obj_scroll_to_y(Obj *o, int y, int) {o->scroll=y;}
void lv_obj_scroll_to_view(Obj *o, int) {++o->visits;}
void lv_obj_update_layout(Obj *) {}
int lv_obj_get_style_height(Obj *o, int) {return o->height;}
int lv_obj_get_style_x(Obj *o, int) {return o->x;}
int lv_obj_get_style_width(Obj *o, int) {return o->width;}
void lv_obj_set_x(Obj *o, int x) {o->x=x;}
void lv_obj_set_width(Obj *o, int w) {o->width=w;}
void lv_obj_center(Obj *) {}
Obj *lv_obj_get_child(Obj *o, int) {return o->child;}
const char *lv_label_get_text(Obj *o) {return o->text.c_str();}
void visible(Obj *o, bool b) {o->shown=b;}
void enabled(Obj *o, bool b) {o->enabled=b;}
void caption(Obj *o, const std::string &s) {o->text=s;}

struct Result {bool done=false;};
struct Set {Result value, left, right; bool per_side=false, warmup=false;};
struct Exercise {uint32_t rest=180; std::vector<Set> sets{Set{}};};
class GymNative {
 public:
  bool plan_fresh() const {return valid_ && fresh;}
  bool fresh=true;
  bool valid_=true, bound_=true, playing_=false, paired_=true, command_busy_=false;
  bool session_button_primary_=true;
  int person_=0, selected_=0, modal_kind_=0, renders=0, requests=0, finish_dialogs=0;
  unsigned session_revision_=8, session_done_=0, session_total_=3;
  unsigned automatic_follows_=0, automatic_rests_=0;
  double session_elapsed_=0;
  float session_volume_=123.45f;
  std::string volume_unit_="kg";
  uint32_t elapsed_received_=0;
  int image_display_width_=512;
  std::string session_id_="session", session_phase_="active", submitted;
  std::vector<Exercise> exercises_{Exercise{}, Exercise{}, Exercise{}};
  std::vector<int> routine_choices_;
  esphome::gym_panel::Timer timer_;
  SetFeedback set_feedback_;
  SetScroll set_scroll_;
  std::array<Obj,22> objects{};
  std::array<Obj*,7> days_{};
  std::array<Obj*,6> controls_{};
  std::vector<Obj*> exercise_buttons_;
  Obj *status_label_=&objects[0], *media_stage_=&objects[1], *session_button_=&objects[2];
  Obj *session_text_=&objects[3], *set_button_=&objects[4], *position_label_=&objects[5];
  Obj *brand_label_=&objects[6], *date_label_=&objects[7], *session_label_=&objects[8];
  Obj *rows_=&objects[9], *volume_title_=&objects[20], *volume_label_=&objects[21];
  GymNative() {
    media_stage_->x=292; media_stage_->width=640;
    set_button_->child=&objects[10]; session_button_->child=session_text_;
    session_button_->primary=true; set_button_->primary=true;
    for (unsigned i=0;i<days_.size();++i) days_[i]=&objects[11];
    for (unsigned i=0;i<controls_.size();++i) {
      controls_[i]=&objects[12+i]; controls_[i]->child=&objects[18];
    }
    exercise_buttons_={&objects[12],&objects[13],&objects[14]};
  }
  void render_session(); void session_action();
  void choose_exercise(int); void apply_set_feedback();
  void close_modal() {if (!command_busy_) modal_kind_=0;}
  void update_status(const char *s) {status_label_->text=s;}
  void render_timer() {}
  void render_exercise() {++renders;}
  void request_media() {++requests;}
  void style_button(Obj *o, bool primary) {o->primary=primary;}
  void show_routines() {submitted="routines";}
  void show_pair() {submitted="pair";}
  void submit(const std::string &s) {submitted=s;}
  void show_finish() {++finish_dialogs;}
  void arm(int ex=0, int row=0, int side=0, bool was_done=false, bool done=true) {
    selected_=ex; modal_kind_=1;
    set_feedback_.arm("session",7,ex,row,side,done,was_done,now);
  }
};
'''
        checks = r'''
int main() {
  // Last set acknowledged: show next exercise, start OLD exercise rest, no save.
  {
    GymNative g; g.exercises_[1].rest=30; g.arm();
    g.exercises_[0].sets[0].value.done=true; g.apply_set_feedback();
    assert(g.selected_==1 && g.modal_kind_==0 && g.requests==1 && g.renders==1);
    assert(g.exercise_buttons_[1]->visits==1 && g.automatic_follows_==1);
    assert(g.timer_.running && g.timer_.deadline==now+180000);
    assert(g.timer_.remaining(now)==180 && g.automatic_rests_==1 && g.submitted.empty());
    g.apply_set_feedback(); assert(g.requests==1 && g.automatic_rests_==1);
  }
  // Do not advance after a non-final work set or a still-pending warmup.
  for (bool warmup : {false,true}) {
    GymNative g; g.exercises_[0].sets.resize(2);
    g.exercises_[0].sets[1].warmup=warmup;
    g.arm(); g.exercises_[0].sets[0].value.done=true; g.apply_set_feedback();
    assert(g.selected_==0 && g.requests==0 && g.automatic_rests_==1);
    g.session_revision_=9; g.arm(0,1);
    g.exercises_[0].sets[1].value.done=true; g.apply_set_feedback();
    assert(g.selected_==1);
  }
  // Both unilateral orders: first side stays, second side advances exactly once.
  for (int first : {1,2}) {
    GymNative g; auto &s=g.exercises_[0].sets[0]; s.per_side=true;
    g.arm(0,0,first); (first==1?s.left:s.right).done=true; g.apply_set_feedback();
    assert(g.selected_==0 && !g.timer_.running);
    g.arm(0,0,3-first); (first==1?s.right:s.left).done=true; g.apply_set_feedback();
    assert(g.selected_==1 && g.automatic_rests_==1);
  }
  // Skip complete/empty exercises; wrap to earlier pending work, not to a done one.
  {
    GymNative g; g.exercises_[1].sets[0].value.done=true;
    g.arm(); g.exercises_[0].sets[0].value.done=true; g.apply_set_feedback();
    assert(g.selected_==2);
    g.exercises_[0].sets[0].value.done=false; g.exercises_[1].sets.clear();
    g.arm(2); g.exercises_[2].sets[0].value.done=true; g.apply_set_feedback();
    assert(g.selected_==0);
  }
  // Final exercise: stay put; finishing still requires the existing confirmation.
  {
    GymNative g; for (auto &e:g.exercises_) e.sets[0].value.done=true;
    g.arm(2); g.session_done_=g.session_total_; g.apply_set_feedback(); g.render_session();
    assert(g.selected_==2 && g.requests==0 && g.session_button_->primary);
    assert(!g.set_button_->primary && !g.set_button_->enabled);
    assert(g.session_text_->text=="Avslutt økt" && g.submitted.empty());
    g.session_action(); assert(g.finish_dialogs==1 && g.submitted.empty());
    // Undo reopens normal registration and removes the finish accent immediately.
    g.exercises_[0].sets[0].value.done=false; --g.session_done_; g.selected_=0;
    g.render_session(); assert(!g.session_button_->primary && g.set_button_->primary);
    assert(g.set_button_->enabled);
  }
  // Stale data, errors/cancel, edits, undo, a different session, navigation and
  // delayed replies cannot unexpectedly move the view or finish a workout.
  for (int scenario=0;scenario<9;++scenario) {
    GymNative g; g.arm(); g.exercises_[0].sets[0].value.done=true;
    if (scenario==0) g.session_revision_=7;
    if (scenario==1) g.set_feedback_.cancel();
    if (scenario==2) g.set_feedback_.was_complete=true;
    if (scenario==3) g.set_feedback_.requested_done=false;
    if (scenario==4) g.session_id_="other";
    if (scenario==5) g.choose_exercise(1);
    if (scenario==6) g.session_phase_="saving";
    if (scenario==7) g.set_feedback_.submitted_at=now-60001;
    if (scenario==8) g.exercises_[0].sets[0].value.done=false;
    int before=g.selected_; g.apply_set_feedback();
    assert(g.selected_==before && !g.timer_.running && g.submitted.empty());
  }
  // An in-flight command keeps its receipt armed; a later authoritative poll
  // recovers a lost reply, but an old revision cannot cause an optimistic jump.
  {
    GymNative g; g.arm(); g.command_busy_=true;
    g.exercises_[0].sets[0].value.done=true; g.apply_set_feedback();
    assert(g.selected_==0 && g.set_feedback_.pending && g.modal_kind_==1);
    g.command_busy_=false; g.session_revision_=7; g.apply_set_feedback();
    assert(g.selected_==0 && g.set_feedback_.pending);
    g.session_revision_=8; g.apply_set_feedback(); assert(g.selected_==1);
  }
  // Zero rest remains zero. Empty lists/invalid state/counter mismatch must
  // not claim completion; idle Start remains the primary action.
  {
    GymNative offline;
    offline.timer_.reset(180); offline.timer_.toggle(now,180);
    const auto deadline=offline.timer_.deadline;
    offline.fresh=false; offline.render_session();
    assert(offline.valid_ && offline.exercises_.size()==3);
    assert(!offline.session_button_->enabled && !offline.set_button_->enabled);
    assert(offline.timer_.running && offline.timer_.deadline==deadline);
    offline.fresh=true; offline.render_session();
    assert(offline.session_button_->enabled && offline.set_button_->enabled);
  }
  {
    GymNative g; g.arm(); g.exercises_[0].rest=0;
    g.exercises_[0].sets[0].value.done=true; g.apply_set_feedback();
    assert(g.selected_==1 && !g.timer_.running && g.automatic_rests_==0);
    for (auto &e:g.exercises_) e.sets[0].value.done=true;
    g.render_session(); assert(!g.session_button_->primary); // Counter mismatch.
    g.session_done_=g.session_total_; g.valid_=false; g.render_session();
    assert(!g.session_button_->primary && !g.session_button_->enabled);
    g.valid_=true; g.exercises_.clear(); g.render_session();
    assert(!g.session_button_->primary && !g.set_button_->enabled);
    g.session_id_.clear(); g.render_session();
    assert(g.session_button_->primary && !g.set_button_->shown);
    assert(!all_exercises_complete(std::vector<Exercise>{}));
    assert(next_pending_exercise(g.exercises_,0)==-1);
  }
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(fixture + production + checks)
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(COMPONENT), str(path / 'test.cpp'),
                            '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True, timeout=10)
