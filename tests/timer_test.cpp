#include "../firmware/custom_components/gym_panel/timer.h"
#include <cassert>
#include <iostream>
using esphome::gym_panel::Timer;
int main(){
 Timer t;t.reset(120);t.toggle(100,120);assert(t.remaining(101)==120);assert(t.remaining(1100)==119);t.adjust(15,1100);assert(t.remaining(1100)==134);t.toggle(2100,120);assert(!t.running&&t.remaining(50000)==133);t.toggle(50000,120);t.tick(183000);assert(!t.running&&t.remaining(183000)==0);
 t.reset(1);t.toggle(0xfffffff0u,1);assert(t.remaining(0x00000010u)==1);t.tick(0x00000400u);assert(t.remaining(0x00000400u)==0);t.reset(3600);t.adjust(15,0);assert(t.remaining(0)==3600);t.adjust(-99999,0);assert(t.remaining(0)==0);t.reset(0);t.toggle(0,0);assert(!t.running);
 std::cout<<"Timer: countdown, pause, adjustment, expiry, bounds and millis wrap passed\n";
}
