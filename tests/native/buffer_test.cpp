#include "../../firmware/custom_components/gym_native/media_buffer.h"
#include <cassert>
#include <cstring>
#include <utility>

using esphome::gym_native::MediaBuffer;

int main() {
  MediaBuffer first;
  assert(!first.allocate(0));
  assert(!first.allocate(MediaBuffer::MAX_BYTES + 1));
  assert(first.allocate(3440652));
  assert(reinterpret_cast<uintptr_t>(first.data() + 12) % 64 == 0);
  std::memset(first.data(), 0xa5, first.size());
  auto *original = first.data();
  assert(!first.allocate(100, [](size_t) -> void * { return nullptr; }));
  assert(first.data() == original && first.size() == 3440652);
  MediaBuffer second = std::move(first);
  assert(first.data() == nullptr && first.size() == 0);
  assert(second.data() == original && second.data()[3440651] == 0xa5);
  first = std::move(second);
  assert(second.size() == 0 && first.data() == original);
  first.reset();
  assert(first.size() == 0 && first.data() == nullptr);
}
