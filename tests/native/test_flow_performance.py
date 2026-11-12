"""Run actual production worker loops with deterministic I/O and task boundaries.

This does not measure physical LCD latency. In particular a blocked conversion
must not block the separate workout command worker or overwrite its handoff.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'firmware/custom_components/gym_native'

class FlowPerformanceTests(unittest.TestCase):
    def compile_run(self, source):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(source)
            subprocess.run(['g++', '-std=c++17', '-pthread', '-Wall', '-Wextra', '-Werror',
                            '-I', str(COMPONENT), str(path/'test.cpp'), '-o', str(path/'test')], check=True)
            subprocess.run([str(path/'test')], timeout=10, check=True)

    def test_progress_pairs_warmups_undo_and_decimal(self):
        self.compile_run(r'''
#include "workout_progress.h"
#include <vector>
#include <cassert>
struct Result { bool done = false; };
struct Set { Result value, left, right; bool warmup = false, per_side = false; };
using namespace esphome::gym_native;
int main() {
  std::vector<Set> sets(4); sets[0].warmup = true;
  auto p = workout_progress(sets);
  assert(p.next_caption() == "Oppv. 1 av 1" && p.work_total == 3 && !p.complete());
  sets[0].value.done = true;
  p = workout_progress(sets); assert(p.next_caption() == "Sett 1 av 3");
  sets[1].per_side = true; sets[1].left.done = true;
  p = workout_progress(sets); assert(p.next_caption() == "Sett 1 av 3 · Høyre" && p.work_done == 0);
  sets[1].right.done = true;
  p = workout_progress(sets); assert(p.next_row == 2 && p.work_done == 1 && p.next_ordinal == 2);
  sets[2].value.done = sets[3].value.done = true;
  p = workout_progress(sets); assert(p.complete() && p.next_caption() == "Fullført");
  sets[1].left.done = false;
  p = workout_progress(sets); assert(!p.complete() && p.next_side == 1 && p.work_done == 2);
  assert(!workout_progress(std::vector<Set>{}).complete());
  assert(decimal_text("7.3 kg") == "7,3 kg");
  assert(decimal_text("2.5–7.25 kg") == "2,5–7,25 kg");
  assert(decimal_text("Oppv. 1") == "Oppv. 1");
}
''')

    def test_actual_media_and_command_workers(self):
        cpp = (COMPONENT/'gym_native.cpp').read_text()
        worker = cpp.split('void GymNative::worker()',1)[1].split('bool GymNative::unpack_media(',1)[0]
        worker = 'void GymNative::worker()'+worker
        media = (COMPONENT/'media_worker.cpp').read_text().split('namespace esphome::gym_native {',1)[1].rsplit('}  // namespace',1)[0]
        prefix = r'''
#include "media_cache.h"
#include <atomic>
#include <cassert>
#include <functional>
#include <thread>
#include <future>
#include <mutex>
#include <vector>
using namespace esphome::gym_native;
static std::atomic<uint32_t> clock_ms{1000};
uint32_t millis() { return clock_ms.load(); }
int pdMS_TO_TICKS(int ms) { return ms; }
struct Stop {};
thread_local std::function<void()> tick;
void vTaskDelay(int) { if (tick) tick(); }
namespace wifi { struct WiFi { bool is_connected() { return true; } } wifi; WiFi *global_wifi_component = &wifi; }
class GymNative {
 public:
  void worker(); void media_worker(); bool media_wanted(uint32_t, const std::string &);
  void lock_request() { mutex.lock(); } void unlock_request() { mutex.unlock(); }
  bool get(const std::string &route, std::string &body, size_t, uint32_t,
           uint32_t = 0, MediaBuffer *data = nullptr, const std::string * = nullptr, int *status = nullptr) {
    if (status) *status = 200;
    body = "command-result";
    if (io) return io(route, data);
    return !data || data->allocate(12);
  }
  bool unpack_media(MediaBuffer &) { return true; }
  std::mutex mutex;
  std::atomic<uint32_t> context_{1}, media_generation_{1};
  std::string wanted_slug_, wanted_media_, wanted_prefetch_, wanted_routine_, wanted_command_;
  int wanted_day_ = -1, pending_kind_ = 0, pending_status_ = 0;
  bool pending_ok_ = false, pending_media_ready_ = false;
  uint32_t pending_context_ = 0, pending_media_context_ = 0, pending_media_generation_ = 0;
  std::string pending_, pending_media_route_;
  SharedMedia pending_binary_;
  std::atomic<bool> session_active_{false}, media_paused_{false}, prefetch_ready_{false};
  std::atomic<bool> plan_retry_{false};
  std::atomic<unsigned> cache_hits_{0}, media_downloads_{0}, prefetch_downloads_{0};
  std::atomic<size_t> cache_bytes_{0}, last_wire_bytes_{0};
  MediaCache cache_;
  std::function<bool(const std::string &, MediaBuffer *)> io;
};
void run(const std::function<void()> &f) { try { f(); } catch (const Stop &) {} }
'''
        tests = r'''
int main() {
  // Foreground first; tap DURING speculative fetch adopts that single transfer.
  {
    GymNative g; g.wanted_media_ = "still"; g.wanted_prefetch_ = "anim";
    std::vector<std::string> requests;
    g.io = [&](const std::string &route, MediaBuffer *data) {
      requests.push_back(route);
      if (route == "anim") { g.wanted_media_ = "anim"; g.wanted_prefetch_ = "still"; ++g.media_generation_; }
      return data->allocate(12);
    };
    int turns = 0;
    tick = [&] { if (++turns == 1) { assert(g.pending_media_route_ == "still"); g.pending_media_ready_ = false; }
                else throw Stop{}; };
    run([&] { g.media_worker(); });
    assert((requests == std::vector<std::string>{"still", "anim"}));
    assert(g.pending_media_generation_ == 2 && g.pending_media_route_ == "anim");
    assert(g.prefetch_downloads_ == 1);
  }
  // Context changed while I/O was in flight: never deliver previous profile.
  {
    GymNative g; g.wanted_media_ = "obsolete";
    g.io = [&](const std::string &, MediaBuffer *data) { ++g.context_; g.wanted_media_ = "new"; return data->allocate(12); };
    tick = [] { throw Stop{}; }; run([&] { g.media_worker(); });
    assert(!g.pending_media_ready_);
  }
  // A permanently unavailable prefetch backs off rather than hammering the host.
  {
    GymNative g; g.wanted_media_ = "still"; g.wanted_prefetch_ = "missing";
    g.io = [](const std::string &r, MediaBuffer *d) { return r != "missing" && d->allocate(12); };
    int turns = 0;
    tick = [&] { g.pending_media_ready_ = false; if (++turns == 4) throw Stop{}; };
    run([&] { g.media_worker(); }); assert(g.prefetch_downloads_ == 1);
  }
  // Sleeping display: no foreground or speculative network work.
  {
    GymNative g; g.wanted_media_ = "still"; g.wanted_prefetch_ = "anim"; g.media_paused_ = true;
    tick = [] { throw Stop{}; }; run([&] { g.media_worker(); });
    assert(g.media_downloads_ == 0 && g.prefetch_downloads_ == 0);
  }
  // Warm local cache needs no HTTP/decompression.
  {
    GymNative g; auto data = std::make_shared<MediaBuffer>(); assert(data->allocate(12));
    g.cache_.put("warm", data); g.wanted_media_ = "warm";
    g.io = [](const std::string &, MediaBuffer *) { assert(false); return false; };
    tick = [] { throw Stop{}; }; run([&] { g.media_worker(); });
    assert(g.cache_hits_ == 1 && g.pending_binary_ == data);
  }
  // Crucial integration boundary: blocked animation does not own the command
  // worker or its pending-result channel. Complete command BEFORE release.
  {
    GymNative g; g.wanted_media_ = "anim";
    std::promise<void> blocked, release; auto released = release.get_future();
    std::atomic<bool> done{false};
    g.io = [&](const std::string &route, MediaBuffer *data) {
      if (data) { blocked.set_value(); released.wait(); return data->allocate(12); }
      assert(route == "/api/profiles/tester/action"); done = true; return true;
    };
    auto thread = std::thread([&] { tick = [] { throw Stop{}; }; run([&] { g.media_worker(); }); });
    blocked.get_future().wait();
    g.lock_request(); g.wanted_slug_ = "tester"; g.wanted_command_ = "register"; g.unlock_request();
    tick = [] { throw Stop{}; }; run([&] { g.worker(); });
    assert(done && g.pending_kind_ == 4 && g.pending_ == "command-result");
    release.set_value(); thread.join();
    assert(g.pending_kind_ == 4 && g.pending_ == "command-result");
  }
}
'''
        self.compile_run(prefix + worker + media + tests)
        # Main-loop command handoff must not steal/empty the media worker channel.
        loop = cpp.split('void GymNative::loop()',1)[1]
        self.assertNotIn('pending_binary_', loop.split('const bool media_ready',1)[0])
        self.assertIn('generation == media_generation_.load()', loop)
        self.assertIn('media_context == context_.load()', loop)
