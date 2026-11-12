# Illustrations and media rights

The software licence and the exercise-media licence are different.

The community edition includes **no standalone Gym visual photos, stills, GIFs,
animations or video files**. The maintainer's expressly authorized README photo
shows a real configured installation; visible third-party artwork is covered by
the [separate photo notice](images/PHOTO-NOTICE.md), not by the code's AGPL.
The installer does not download, hotlink or extract media from OpenGym containers
or a running server. The adapter's default `mediaMode` is `placeholder`, returning
original geometric dumbbell artwork in the normal bounded display format. The
workout name, target sets and muscle map still describe the selected exercise;
the placeholder does not pretend to teach movement technique.

OpenGym's [pinned media notice](https://github.com/DuarteSantos8/openGym/blob/5f5832db56080837b58342ff50f78631dcc63e07/NOTICE.md#exercise-media-stills-and-animations)
sets separate conditions for Gym visual's assets. OpenGym's AGPL does not grant
permission to integrate those assets into this independent display. Merely
having access to your own OpenGym server is not a blanket media-reuse licence.

## Optional media that you own or are licensed to integrate

Only after establishing the necessary rights, set `mediaMode` to `owned` in your
**private** generated `native.json` and place files in its `owned-media/` folder.
The adapter reads only pinned allowlisted local filenames. `native/catalogue-modern.json`
maps display aliases to `still/<id>.webp` and `clip/<id>.mp4`; older aliases use
`img/` and `gif/` names in `native/catalogue-media.json`. These JSON files contain
metadata/path mappings, not media assets. Supply your own matching illustrations;
there is deliberately no bundled media-fetch or extraction tool.

Converters limit sizes, dimensions, frame count, decoder time and cache memory;
symlinks, traversal and arbitrary URLs are rejected. Author-owned synthetic
images/video are used in converter tests. Do not attach restricted assets or
real training photographs to public issues or releases.

The muscle-map masks have separate MIT provenance preserved in
`MUSCLEMAP-LICENSE.txt`; they are not generated from Gym visual media.
