#pragma once
#include <cstddef>
#include <string>

namespace esphome::gym_native {
enum class Handoff { NONE, SAVED, CLOSED, DISCARDED };

// A closed session is not a guessed save. Require the server's verified result
// for the session we were displaying, including recovery after a lost HTTP ack.
inline Handoff completed_handoff(const std::string &previous, const std::string &current,
                                 const std::string &result, const std::string &result_session,
                                 const std::string &action) {
  if (previous.empty() || !current.empty()) return Handoff::NONE;
  if (result_session == previous) {
    if (result == "saved") return Handoff::SAVED;
    if (result == "closed") return Handoff::CLOSED;
  }
  // Existing explicit-discard replies have no sessionId. They are accepted only
  // in the current profile/context after our own confirmed discard request.
  if (result == "discarded" && action == "discard") return Handoff::DISCARDED;
  return Handoff::NONE;
}

inline const char *handoff_caption(Handoff result) {
  switch (result) {
    case Handoff::SAVED: return "Økten er lagret i OpenGym";
    case Handoff::CLOSED: return "Økten er avsluttet uten lagring";
    case Handoff::DISCARDED: return "Økten er forkastet";
    default: return "Klar for trening";
  }
}

struct PersonTile { int x, y, width, height; };
// 1080 px list, two equally sized controls; an unpaired last card is centred.
inline PersonTile person_tile(size_t count, size_t index) {
  const bool alone = count % 2 == 1 && index + 1 == count;
  return {alone ? 276 : static_cast<int>(index % 2) * 552,
          static_cast<int>(index / 2) * 184, 528, 160};
}
}  // namespace esphome::gym_native
