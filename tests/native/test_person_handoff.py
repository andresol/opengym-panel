"""Execute production picker/reset logic and its terminal-result policy on a host.

Recording objects are not LVGL or a physical touchscreen. Existing worker tests
separately exercise rejection of in-flight responses after the context changes.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'firmware/custom_components/gym_native'


class PersonHandoffTests(unittest.TestCase):
    def test_confirmed_finish_and_real_picker_reset(self):
        source = (COMPONENT / 'gym_native.cpp').read_text()
        production = source.split('void GymNative::clear_plan(', 1)[1].split('void GymNative::choose_day(', 1)[0]
        production = 'void GymNative::clear_plan(' + production
        prefix = r'''
#include "ui_text.h"
esphome::gym_native::UiText ui_;
#include "person_handoff.h"
#include "timer.h"
#include <array>
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
using namespace esphome::gym_native;
constexpr int LV_ANIM_OFF = 0;
struct Obj { bool hidden = false; std::string text; int scroll = 77; };
void set_text(Obj *o, const std::string &s) {o->text=s;}
void hidden(Obj *o, bool value) {o->hidden=value;}
void lv_obj_scroll_to_y(Obj *o,int y,int) {o->scroll=y;}
struct Feedback { bool cancelled = false; void cancel() {cancelled=true;} };
class GymNative {
 public:
  void clear_plan(const char *);
  void reset_connection() {connection_reset=true;}
  void picker(Handoff completion=Handoff::NONE);
  void choose_person(int);
  void close_modal() {++modal_closes;}
  void lock_request() {} void unlock_request() {}
  void hide_media() {media_hidden=true;}
  void render_plan() {++renders;}
  void render_muscles() {}
  void update_status(const char *text,bool=false) {status=text;}
  struct Person {std::string slug,name;};
  std::vector<Person> people_{{"alpha","Alpha"},{"beta","Beta"}};
  bool command_busy_=false,session_active_=true,paired_=true,valid_=true,playing_=true;
  bool prefetch_ready_=true,media_hidden=false;
  bool connection_reset=false;
  int person_=0,day_=4,selected_=3,modal_closes=0,renders=0;
  unsigned session_revision_=8,session_done_=10,session_total_=12;
  double session_elapsed_=200;
  float session_volume_=123; std::string volume_unit_="kg";
  std::string session_id_="finished-session",session_phase_="active",command_action_="finish";
  std::string wanted_slug_="alpha",wanted_routine_="old-choice",selected_routine_="old-choice";
  std::string wanted_media_="old-image",wanted_prefetch_="old-animation";
  std::string title_="old-workout",date_="old-date",revision_="old-revision",status;
  int wanted_day_=4;
  unsigned context_=7,media_generation_=4;
  std::array<bool,7> week_{{true,true,true,true,true,true,true}};
  std::vector<int> exercises_{1,2,3,4},routine_choices_{1};
  Feedback set_feedback_;
  Handoff pending_handoff_=Handoff::SAVED;
  esphome::gym_panel::Timer timer_;
  Obj person_text,people_list,welcome_status,welcome_heading,workout,welcome,person_button,media_empty;
  Obj *person_text_=&person_text,*people_list_=&people_list,*welcome_status_=&welcome_status;
  Obj *welcome_heading_=&welcome_heading,*workout_=&workout,*welcome_=&welcome;
  Obj *person_button_=&person_button,*media_empty_=&media_empty;
};
'''
        tests = r'''
int main() {
  assert(completed_handoff("s","","saved","s","finish")==Handoff::SAVED);
  assert(completed_handoff("s","","saved","s","")==Handoff::SAVED); // Lost command ACK, ordinary readback.
  assert(completed_handoff("s","","closed","s","finish")==Handoff::CLOSED);
  assert(completed_handoff("s","","discarded","","discard")==Handoff::DISCARDED);
  assert(completed_handoff("s","s","saved","s","finish")==Handoff::NONE); // Still saving/active.
  assert(completed_handoff("s","","saved","other","finish")==Handoff::NONE);
  assert(completed_handoff("s","","saved","","finish")==Handoff::NONE);
  assert(completed_handoff("s","","closed","other","finish")==Handoff::NONE);
  assert(completed_handoff("s","","discarded","","finish")==Handoff::NONE);
  assert(completed_handoff("s","","save_unconfirmed","s","finish")==Handoff::NONE);
  assert(completed_handoff("s","","","","finish")==Handoff::NONE);
  assert(completed_handoff("","","saved","s","finish")==Handoff::NONE); // Never repeat on idle/new-person fetch.
  assert(std::string(handoff_caption(Handoff::CLOSED)).find("lagret")==std::string::npos);
  assert(std::string(handoff_caption(Handoff::DISCARDED)).find("lagret")==std::string::npos);
  GymNative g; g.timer_.reset(180);g.timer_.toggle(1000,180);
  g.picker(Handoff::SAVED);
  assert(g.connection_reset);
  assert(g.person_==-1 && !g.valid_ && !g.paired_ && !g.session_active_ && g.session_id_.empty());
  assert(g.session_done_==0 && g.session_revision_==0 && g.session_elapsed_==0);
  assert(g.session_volume_==0 && g.volume_unit_.empty());
  assert(g.wanted_slug_.empty() && g.wanted_day_==-1 && g.wanted_routine_.empty());
  assert(g.context_==8 && g.media_generation_==5 && g.wanted_media_.empty() && g.wanted_prefetch_.empty());
  assert(!g.prefetch_ready_ && g.media_hidden && g.set_feedback_.cancelled);
  assert(g.exercises_.empty() && g.routine_choices_.empty() && !g.playing_ && g.day_==-1);
  assert(!g.timer_.running && g.timer_.remaining(1000)==0);
  assert(g.workout.hidden && !g.welcome.hidden && g.person_button.hidden && g.people_list.scroll==0);
  assert(g.welcome_status.text=="Økten er lagret i OpenGym" && g.welcome_heading.text=="Hvem skal trene nå?");
  assert(g.pending_handoff_==Handoff::NONE && g.people_.size()==2 && g.command_action_.empty());
  for(bool day:g.week_)assert(!day);
  g.choose_person(1);
  assert(g.person_==1 && g.wanted_slug_=="beta" && g.context_==9 && g.wanted_day_==-1);
  assert(g.welcome.hidden && !g.workout.hidden && !g.person_button.hidden && g.person_text.text=="Beta");
  assert(g.exercises_.empty() && g.session_id_.empty()); // Must fetch fresh Beta plan; no Alpha fallback.
  g.picker();assert(g.welcome_status.text=="Klar for trening" && g.welcome_heading.text=="Hvem skal trene?");
  GymNative busy;busy.command_busy_=true;busy.picker(Handoff::SAVED);
  assert(busy.person_==0 && busy.session_id_=="finished-session" && busy.context_==7);
  busy.choose_person(1);assert(busy.person_==0 && busy.context_==7);
  GymNative invalid;invalid.choose_person(8);assert(invalid.person_==0 && invalid.context_==7);
  for(size_t count=1;count<=8;++count) {
    for(size_t i=0;i<count;++i) {
      auto tile=person_tile(count,i);
      assert(tile.x>=0 && tile.x+tile.width<=1080 && tile.width==528 && tile.height==160);
      assert(tile.y==int(i/2)*184);
      if(count<=4)assert(tile.y+tile.height<=344);
      if(count%2==1 && i+1==count)assert(tile.x==276);
    }
  }
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(prefix + production + tests)
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(COMPONENT),
                            str(path / 'test.cpp'), '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True, timeout=10)

        acceptance = source.split('bool GymNative::accept_plan(', 1)[1].split('void GymNative::update_status', 1)[0]
        self.assertLess(acceptance.index('text(root["profileSlug"]'), acceptance.index('completed_handoff('))
        self.assertIn('if (!session_id_.empty() && session.empty()) return false;', acceptance)
        loop = source.split('void GymNative::loop()', 1)[1]
        self.assertIn('people_list_ = box(welcome_, 100, 240, 1080, 344, BG, true)', source)
        self.assertIn('!command_busy_ && pending_handoff_ != Handoff::NONE', loop)
        self.assertLess(loop.index('picker(completion)'), loop.index('const bool media_ready'))
