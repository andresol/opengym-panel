#pragma once
#include <algorithm>
#include <cstdint>
namespace esphome { namespace gym_panel {
struct Timer {
  uint32_t deadline=0, seconds=0; bool running=false;
  uint32_t remaining(uint32_t now) const {
    if(!running) return seconds;
    const int32_t delta=static_cast<int32_t>(deadline-now);
    return delta<=0?0:(static_cast<uint32_t>(delta)+999)/1000;
  }
  void reset(uint32_t value) {seconds=std::min<uint32_t>(value,3600u);running=false;}
  void toggle(uint32_t now,uint32_t fallback) {
    if(running){seconds=remaining(now);running=false;}
    else {if(!seconds)seconds=fallback;deadline=now+seconds*1000;running=seconds>0;}
  }
  void adjust(int delta,uint32_t now) {
    seconds=static_cast<uint32_t>(std::max(0,std::min(3600,static_cast<int>(remaining(now))+delta)));
    if(running){deadline=now+seconds*1000;running=seconds>0;}
  }
  void tick(uint32_t now){if(running && remaining(now)==0){running=false;seconds=0;}}
};
}}
