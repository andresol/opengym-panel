"""Run the actual picker methods with recording LVGL calls, not a real LCD."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'firmware/custom_components/gym_native'


class WeightPickerTests(unittest.TestCase):
    def test_picker_lifecycle_and_local_only_changes(self):
        source = (COMPONENT / 'weight_picker.cpp').read_text().replace('#include "gym_native.h"', '')
        harness = r'''
#include "ui_text.h"
esphome::gym_native::UiText ui_;

#include "weight_control.h"
#include "ui_style.h"
#include <cassert>
#include <memory>
struct Obj {
  std::string text; int x=0,y=0,w=0,h=0,action=0,arg=0; bool disabled=false,deleted=false;
  std::vector<Obj*> children;
};
using lv_obj_t = Obj;
constexpr int LV_TEXT_ALIGN_CENTER=0, LV_STATE_DISABLED=1;
std::vector<std::unique_ptr<Obj>> storage;
Obj* make(Obj* p,const char* text,int x,int y,int w,int h) {
  storage.emplace_back(new Obj); auto* o=storage.back().get();
  o->text=text;o->x=x;o->y=y;o->w=w;o->h=h;
  if(p)p->children.push_back(o);
  return o;
}
void lv_obj_delete(Obj* o) {o->deleted=true;}
void lv_label_set_text(Obj* o,const char* text) {o->text=text;}
Obj* lv_obj_get_child(Obj* o,unsigned i) {return o->children.at(i);}
int lv_color_hex(int c) {return c;}
void lv_obj_set_style_text_font(Obj*,int,int) {}
void lv_obj_set_style_text_align(Obj*,int,int) {}
void lv_obj_set_style_text_color(Obj*,int,int) {}
void lv_obj_set_style_border_color(Obj*,int,int) {}
void lv_obj_set_style_border_width(Obj*,int,int) {}
void lv_obj_center(Obj*) {}
void lv_obj_add_state(Obj* o,int) {o->disabled=true;}
void lv_obj_remove_state(Obj* o,int) {o->disabled=false;}
namespace esphome::gym_native {
struct Exercise {std::vector<float> weight_options{0, 4.5f, 9.1f, 13.6f, 18.1f, 22.7f, 27.2f, 31.8f, 36.3f, 40.8f, 45.4f, 50.0f, 54.4f, 59.0f, 63.5f, 68.0f, 72.6f, 77.1f, 81.6f, 86.2f, 90.7f, 95.3f};float weight_step=4.55f,weight_max=95.3f;std::string unit="kg";};
struct Result {float weight=13.65f,reps=12;bool done=false;};
class GymNative {
 public:
  void show_weight_picker(int manual=0);void close_weight_picker();void choose_weight(int index);
  void weight_key(int key);void use_weight();
  bool command_busy_=false,valid_=true;int modal_kind_=1,selected_=0;
  Obj* modal_=make(nullptr,"",0,0,1280,800);
  std::vector<Exercise> exercises_{{}};Obj* result_labels_[1]={modal_};
  unsigned binding_count_=145,weight_binding_start_=0;
  Obj *weight_picker_=nullptr,*weight_input_=nullptr,*weight_apply_=nullptr,*weight_error_=nullptr;
  WeightEntry weight_entry_;Result editing_value_;int renders=0;
  int large_=42,heading_=30,normal_=20;
  void update_editor() {++renders;}
  Obj* box(Obj* p,int x,int y,int w,int h,int) {return make(p,"",x,y,w,h);}
  Obj* label(Obj* p,const char* t,int x,int y,int w,int h,int,int=TEXT) {return make(p,t,x,y,w,h);}
  Obj* button(Obj* p,const char* t,int x,int y,int w,int h,int a,int v=0,bool=false) {
    auto* b=make(p,"",x,y,w,h);b->action=a;b->arg=v;++binding_count_;
    make(b,t,8,0,w-16,h);return b;
  }
};
}
'''
        assertions = r'''
using namespace esphome::gym_native;
int main() {
  GymNative p;
  const auto before=p.editing_value_;
  p.show_weight_picker();
  assert(p.weight_picker_ && !p.weight_input_ && p.binding_count_==169);
  int count=0;
  for(auto* b:p.weight_picker_->children) {
    assert(b->x>=0 && b->y>=0 && b->x+b->w<=1280 && b->y+b->h<=800);
    if(b->action==29) {assert(b->w>=258 && b->h>=64);++count;}
  }
  assert(count==22);
  p.choose_weight(99);assert(p.editing_value_.weight==before.weight);
  p.close_weight_picker();assert(p.binding_count_==145 && p.editing_value_.weight==before.weight);
  for(int i=0;i<100;++i) {p.show_weight_picker();p.close_weight_picker();assert(p.binding_count_==145);}
  p.show_weight_picker();p.choose_weight(3);
  assert(p.editing_value_.weight==13.6f && !p.weight_picker_ && p.renders==1);
  p.show_weight_picker();p.choose_weight(21);assert(p.editing_value_.weight==95.3f);
  p.show_weight_picker();p.choose_weight(0);assert(p.editing_value_.weight==0);
  p.editing_value_.weight=7.255f;
  p.show_weight_picker();p.show_weight_picker(1); // cable override: replace overlay, no binding leak
  assert(p.weight_input_ && p.binding_count_==159);
  p.use_weight();assert(p.editing_value_.weight==7.255f);
  p.exercises_[0].weight_step=0;p.exercises_[0].unit="lb";
  p.show_weight_picker();assert(p.weight_input_);
  p.weight_key('7');p.weight_key(',');p.weight_key('3');
  assert(p.editing_value_.weight==7.255f && p.weight_input_->text=="7,3 lb");
  p.close_weight_picker();assert(p.editing_value_.weight==7.255f);
  p.show_weight_picker();p.weight_key('7');p.weight_key(',');p.weight_key('3');p.use_weight();
  assert(p.editing_value_.weight==7.3f && p.editing_value_.reps==12 && !p.editing_value_.done);
  p.show_weight_picker();
  while(!p.weight_entry_.text.empty())p.weight_key(-1);
  assert(p.weight_apply_->disabled);p.use_weight();assert(p.weight_picker_ && p.editing_value_.weight==7.3f);
  p.weight_key('0');assert(!p.weight_apply_->disabled);p.use_weight();assert(p.editing_value_.weight==0);
  p.command_busy_=true;p.show_weight_picker();assert(!p.weight_picker_);
  p.command_busy_=false;p.valid_=false;p.show_weight_picker();assert(!p.weight_picker_);
  p.valid_=true;p.modal_kind_=2;p.show_weight_picker();assert(!p.weight_picker_);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'picker.cpp'
            binary = Path(directory) / 'picker'
            cpp.write_text(harness + source + assertions)
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(COMPONENT),
                            str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_wire_labels_and_event_routes(self):
        click = (COMPONENT / 'gym_native.cpp').read_text()
        for action, method in [(27, 'show_weight_picker'), (28, 'close_weight_picker'),
                               (29, 'choose_weight'), (30, 'weight_key'), (31, 'use_weight')]:
            self.assertRegex(click, rf'case {action}: self->{method}\(')
        ui = (COMPONENT / 'workout_ui.cpp').read_text()
        self.assertIn('button(card, "", 132, 96, 272, 80, 27)', ui)
        close = ui.split('void GymNative::close_modal()', 1)[1].split('void GymNative::show_finish()', 1)[0]
        self.assertLess(close.index('close_weight_picker();'), close.index('lv_obj_delete(modal_)'))
        picker = (COMPONENT / 'weight_picker.cpp').read_text()
        self.assertNotIn('submit(', picker)
        self.assertNotIn('editing_value_.done =', picker)
        self.assertNotIn('session_revision_ =', picker)
