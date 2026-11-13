# One development workflow

The community edition and the maintainer's private installation are kept in
step. Common source files are synchronized byte-for-byte; files with necessary
edition-specific changes are explicitly reviewed and ported. The maintainer's
private tooling blocks unresolved source conflicts and unclassified additions.

Generic installation defaults are not a copy of a household setup: DHCP,
authenticated administration, explicit optional equipment tables and original
placeholder media remain the defaults here. Private credentials, user data,
provisioned firmware, standalone restricted media and private Git history stay outside this
repository. Public contributions are tested here before the maintainer ports
them to the production source; no blind bidirectional directory mirroring is used.

The numeric base version identifies related source lines, for example production
`1.1.33` and community `1.1.33-community.2`. Community suffixes describe generic
installer/documentation revisions. They do not prove that a private device is
running that source. Existing releases remain immutable snapshots; a new commit
does not silently replace an older release archive.

Source sync, tests, firmware builds, remote pushes and actual hardware deployment
are separate results. CI never flashes a device or changes training data.

## README renders

The main README uses clean native renders with fictional profiles and workout
values, not the maintainer's installation photo. The workout render shows the
original exercise still, not an AI imitation. See [provenance and rights](images/RENDER-NOTICE.md).

README PNGs are off-device LVGL renders with synthetic profiles, loads and session
state. They are not photographs, captured ESP32 framebuffers or physical touch
acceptance. Native widget construction/render methods and the bundled font are
used; network, hardware and session storage are not connected. The optional
muscle-map popup is outside this documentation harness.

To reproduce, provide a host-built LVGL **9.5.0** with snapshot/RGB888 support
and its matching configuration. Install `Pillow` and `freetype-py` in an isolated
development environment, then run:

```sh
python3 tools/render_readme.py --language en \
  --lvgl-include /path/to/lvgl \
  --lvgl-library /path/to/build/lib/liblvgl.a \
  --lvgl-config /path/to/lv_conf.h
```

Without `--exercise-image`, the workout render uses the generic placeholder.
To reproduce the documented optional-media view, add `--exercise-image` pointing
to a lawfully supplied barbell-full-squat still (catalogue ID `0043`). The existing
native adapter converts it to the screen's 512×360 RGB565 still format. Only the
complete interface render is written to documentation; the input asset is never
copied into this repository or downloaded by the renderer. The original artwork
has separate rights, and this tooling does not grant a licence to acquire it.

Review every PNG and its fixture/source provenance before committing its hash
in `docs/images/manifest.json`. The public artifact audit allows only those
specific PNG paths, hashes and dimensions and rejects metadata-bearing images.
