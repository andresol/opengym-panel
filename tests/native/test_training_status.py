"""Execute production row rendering and timer styling against recording LVGL calls.

Checks state, row bindings, child contrast and pressed-role selection. This host
harness is not a real LVGL layout engine or a physical LCD/touch test.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'firmware/custom_components/gym_native'

class TrainingStatusTests(unittest.TestCase):
    def test_actual_row_and_timer_rendering(self):
        cpp = (COMPONENT/'gym_native.cpp').read_text()
        rows = cpp.split('  const auto columns =', 1)[1].split('  lv_obj_update_layout(rows_);', 1)[0]
        rows = '  const auto columns =' + rows
        timer = cpp.split('void GymNative::render_timer() {', 1)[1].split('\n}', 1)[0]
        style = cpp.split('void GymNative::style_button(', 1)[1].split('\n}', 1)[0]
        style = 'void style_button(' + style + '\n}\n'
        prefix = r'''
#include "ui_text.h"
esphome::gym_native::UiText ui_;
#include "workout_progress.h"
#include "ui_style.h"
#include "timer.h"
#include <cassert>
#include <cstdio>
#include <memory>
#include <string>
#include <vector>
using namespace esphome::gym_native;
constexpr int LV_SIZE_CONTENT=-1, LV_TEXT_ALIGN_LEFT=0, LV_STATE_PRESSED=1;
constexpr int LV_OBJ_FLAG_CLICKABLE=1;
struct Obj {
  std::string text; int x=0,y=0,w=0,h=0, action=0,arg=0,font=16;
  uint32_t color=TEXT,bg=0,pressed=0; bool invisible=false;
  std::vector<Obj*> children;
};
using lv_obj_t=Obj;
std::vector<std::unique_ptr<Obj>> storage;
Obj *make(Obj *p,int x,int y,int w,int h) {
  storage.emplace_back(new Obj); auto *o=storage.back().get();
  o->x=x; o->y=y; o->w=w; o->h=h;
  if(p) p->children.push_back(o);
  return o;
}
uint32_t lv_color_hex(uint32_t x) {return x;}
void lv_obj_set_style_bg_color(Obj *o,uint32_t c,int state) {if(state) o->pressed=c; else o->bg=c;}
void lv_obj_set_style_text_color(Obj *o,uint32_t c,int) {o->color=c;}
void lv_obj_set_style_text_align(Obj *,int,int) {}
void lv_obj_set_height(Obj *o,int h) {o->h=h==LV_SIZE_CONTENT?(o->font==20?24:19):h;}
void lv_obj_set_y(Obj *o,int y) {o->y=y;}
int lv_obj_get_height(Obj *o) {return o->h;}
void lv_obj_update_layout(Obj *) {}
void lv_obj_remove_flag(Obj *,int) {}
Obj *lv_obj_get_child(Obj *o,unsigned i) {return o->children.at(i);}
void hidden(Obj *o,bool h) {o->invisible=h;}
void set_text(Obj *o,const std::string &s) {o->text=s;}
Obj *label(Obj *p,const char *t,int x,int y,int w,int h,int font,uint32_t c=TEXT) {
  auto *o=make(p,x,y,w,h);o->text=t;o->color=c;o->font=font;return o;
}
Obj *box(Obj *p,int x,int y,int w,int h,uint32_t c) {auto *o=make(p,x,y,w,h);o->bg=c;return o;}
'''
        fixture = r'''
Obj *button(Obj *p,const char *s,int x,int y,int w,int h,int action,int arg,bool primary) {
  auto *o=make(p,x,y,w,h);o->action=action;o->arg=arg;
  label(o,s,8,0,w-16,h,0);style_button(o,primary);return o;
}
struct Result {bool done=false;double weight=70,reps=8,seconds=30,minutes=2;};
struct Set {bool warmup=false,per_side=false;Result value,left,right;};
struct Row {std::string name,load="70 kg",target="8 reps";};
struct Exercise {std::string mode="reps",unit="kg";std::vector<Row> rows;std::vector<Set> sets;};
std::string weight_caption(double v,const std::string &unit) {return std::to_string(int(v))+" "+unit;}
void render(Exercise *e,const std::string &session_id_,Obj *rows_) {
 int row_y=0,small_=16,normal_=20;
'''
        tests = r'''
}
uint32_t now_=1000;
uint32_t millis() {return now_;}
struct Screen {
 esphome::gym_panel::Timer timer_; Obj *timer_label_=make(nullptr,0,0,204,54),*timer_text_=make(nullptr,0,0,300,64);
 void render_timer() {
TIMER_BODY
 }
};
std::vector<Obj*> interactive(Obj *root) {
 std::vector<Obj*> out;for(auto *c:root->children)if(c->action==12)out.push_back(c);return out;
}
Obj *check(Exercise &e,int expected_arg) {
 auto *root=make(nullptr,0,0,300,240);render(&e,"draft",root);
 auto buttons=interactive(root);int next_count=0;
 for(auto *b:buttons) {
  assert(b->w==292 && b->h==54 && b->x==0 && b->y%62==0);
  const bool next=b->arg==expected_arg;
  assert(b->pressed==(next?PRIMARY_PRESSED:SECONDARY_PRESSED));
  for(unsigned i=1;i<b->children.size();++i) {
   auto *c=b->children[i];assert(c->x==10 || c->x==102 || c->x==194);
   assert(c->y>=0 && c->y+c->h<=54);
   if(next) assert(c->color==PRIMARY_TEXT);
  }
  if(next) {
   ++next_count;assert(b->bg==ACCENT && b->children.size()==5);
   assert(b->children[4]->text=="NESTE");
   assert(b->children[1]->y==7 && b->children[4]->y==28);
  } else {
   for(auto *c:b->children)assert(c->text!="NESTE");
   assert(b->bg==SURFACE || b->bg==SELECTED);
  }
 }
 assert(next_count==(expected_arg<0?0:1));return root;
}
int main() {
 Exercise e;e.rows={{"Oppv. 1"},{"Oppv. 2"},{"Sett 1"},{"Sett 2"}};e.sets.resize(4);
 e.sets[0].warmup=e.sets[1].warmup=true;
 check(e,0); e.sets[0].value.done=true;auto *root=check(e,3);
 auto completed=interactive(root)[0];assert(completed->bg==SELECTED);
 assert(completed->children[4]->text=="✓" && completed->children[4]->color==ACCENT);
 assert(completed->children[4]->font==20 && completed->children[4]->h==24);
 assert(completed->children[1]->y==4 && completed->children[4]->y==25);
 e.sets[1].value.done=true;check(e,6); // Warmups advance into first work set.
 e.sets[2].per_side=true;check(e,7);
 e.sets[2].left.done=true;root=check(e,8);
 assert(interactive(root)[3]->children[1]->text=="Sett 1 H");
 e.sets[2].right.done=true;e.sets[3].value.done=true;check(e,-1);
 e.sets[2].left.done=false;check(e,7); // Undo restores earlier left-side target.
 e.sets[2].right.done=false;e.sets[2].left.done=true;check(e,8);
 // Idle preview never marks a next row, even if a draft was previously visible.
 root=make(nullptr,0,0,300,240);render(&e,"",root);
 for(auto *c:root->children) {assert(c->text!="NESTE");assert(c->action!=12);}
 Exercise empty;check(empty,-1);
 // Production timer view: running, stopped, reset, zero and expiry transitions.
 Screen s;s.timer_.reset(180);s.render_timer();
 assert(s.timer_label_->text=="03:00" && s.timer_label_->color==TEXT);
 s.timer_.toggle(now_,180);now_+=1000;s.render_timer();
 assert(s.timer_label_->text=="02:59" && s.timer_label_->color==ACCENT);
 assert(s.timer_text_->text=="Stopp pause");
 s.timer_.toggle(now_,180);s.render_timer();assert(s.timer_label_->color==TEXT);
 assert(s.timer_text_->text=="Start pause");
 s.timer_.reset(180);s.render_timer();assert(s.timer_label_->color==TEXT);
 s.timer_.reset(0);s.timer_.toggle(now_,0);s.render_timer();
 assert(s.timer_label_->text=="00:00" && s.timer_label_->color==TEXT);
 s.timer_.reset(1);s.timer_.toggle(now_,1);now_+=1000;s.render_timer();
 assert(s.timer_label_->color==TEXT); // No false running colour at exact deadline.
 s.timer_.tick(now_);s.render_timer();assert(s.timer_text_->text=="Start på nytt");
 s.timer_.reset(3600);s.render_timer();assert(s.timer_label_->text=="60:00");
}
'''.replace('TIMER_BODY', timer)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'test.cpp').write_text(prefix + style + fixture + rows + tests)
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',
                            '-I',str(COMPONENT),str(path/'test.cpp'),'-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True,timeout=10)
