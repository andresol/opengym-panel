# Native interface documentation renders

`workout.png` and `profiles.png` are 1280×800 offline LVGL desktop renders in English.
The panel's native widget construction/render methods and bundled font are used.
Profile names, workout values, date and session state are fictional. They are
not photographs, physical framebuffer captures or hardware-acceptance evidence.
No AI image generation or retouching is used.

The workout shows the original barbell-full-squat still, catalogue ID `0043`,
from the pinned OpenGym 1.4.4 catalogue. The existing native media converter
produces the same 512×360 RGB565 frame format used on the panel; LVGL binds,
centres and displays it in the unchanged media viewport. Source and output
hashes are recorded in `manifest.json`. The input media is not bundled.

## Separate artwork rights

The visible exercise illustration is © Aliaksandr Makatserchyk / Gym visual.
It is **not licensed under this project's AGPL**. This documentation image does
not grant a right to extract or reuse the exercise illustration. No standalone
Gym visual asset or reusable media collection is distributed here.

See [OpenGym's pinned media notice](https://github.com/DuarteSantos8/openGym/blob/5f5832db56080837b58342ff50f78631dcc63e07/NOTICE.md#exercise-media-stills-and-animations)
and [Gym visual's licence](https://gymvisual.com/content/9-license).
Neither expressly resolves this README screenshot use. Attribution alone is
not permission, and this notice does not claim a special screenshot exemption
or a transfer of OpenGym's media licence to the companion project.

The generic installer continues to use its original geometric placeholder;
this screenshot does not claim that exercise media ships with the installer.
