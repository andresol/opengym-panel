#include "../../firmware/custom_components/gym_native/media_cache.h"
#include "../../firmware/custom_components/gym_native/media_format.h"
#include <cassert>
#include <cstring>

using namespace esphome::gym_native;

SharedMedia media(size_t bytes) {
  auto result = std::make_shared<MediaBuffer>();
  assert(result->allocate(bytes));
  std::memset(result->data(), 0, bytes);
  return result;
}

int main() {
  MediaCache cache(400);
  auto a = media(100), b = media(150), c = media(200);
  cache.put("still/a", a);
  cache.put("still/b", b);
  assert(cache.bytes() == 250 && cache.size() == 2);
  auto displayed = cache.find("still/a");
  assert(displayed == a);  // Reuse pixels, not a second multi-MB allocation.
  cache.put("animation/c", c);
  assert(!cache.find("still/b") && cache.find("still/a"));
  assert(cache.bytes() == 300 && cache.size() == 2);
  cache.put("still/a", c);
  assert(cache.bytes() == 400 && cache.size() == 2);
  cache.put("still/d", media(400));
  assert(cache.size() == 1 && !cache.find("still/a"));
  a.reset();
  assert(displayed->size() == 100 && displayed->data()[99] == 0);
  cache.put("oversized", media(401));
  cache.put("null", {});
  assert(cache.bytes() == 400 && cache.size() == 1);

  MediaCache count_bound;
  for (unsigned n = 0; n < 100; ++n) count_bound.put(std::to_string(n), media(12));
  assert(count_bound.size() == MediaCache::ENTRY_LIMIT);
  assert(!count_bound.find("0") && count_bound.find("99"));

  // HQ downloads reclaim only unreferenced cache entries. Never release the
  // currently displayed buffer, even when the cache sheds its stale frames.
  MediaCache hq_cache;
  auto visible = media(12 + 512 * 360 * 2);
  hq_cache.put("visible", visible);
  hq_cache.put("obsolete", media(MediaBuffer::MAX_BYTES));
  hq_cache.discard_unused();
  assert(hq_cache.size() == 1 && hq_cache.find("visible") == visible);
  assert(!hq_cache.find("obsolete") && visible->size() > 12);
  auto animation = media(MediaBuffer::MAX_BYTES);
  const uint8_t hq_header[] = {'G', 'Y', 'M', '1', 0, 2, 104, 1, 24, 0, 150, 0};
  std::memcpy(animation->data(), hq_header, 12);
  assert(valid_media(animation->data(), animation->size()));
  animation->data()[8] = 25;
  assert(!valid_media(animation->data(), animation->size()));

  auto still = media(12 + 512 * 360 * 2);
  const uint8_t header[] = {'G', 'Y', 'M', '1', 0, 2, 104, 1, 1, 0, 0, 0};
  std::memcpy(still->data(), header, 12);
  assert(valid_media(still->data(), still->size()));
  assert(!valid_media(still->data(), still->size() - 1));
  assert(!valid_media(nullptr, still->size()));
  still->data()[8] = 255;
  assert(!valid_media(still->data(), still->size()));
  still->data()[4] = 255; still->data()[5] = 255;
  assert(!valid_media(still->data(), still->size()));
}
