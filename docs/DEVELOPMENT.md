# One development workflow

The community edition and the maintainer's private installation are kept in
step. Common source files are synchronized byte-for-byte; files with necessary
edition-specific changes are explicitly reviewed and ported. The maintainer's
private tooling blocks unresolved source conflicts and unclassified additions.

Generic installation defaults are not a copy of a household setup: DHCP,
authenticated administration, explicit optional equipment tables and original
placeholder media remain the defaults here. Private credentials, user data,
provisioned firmware, restricted media and private Git history stay outside this
repository. Public contributions are tested here before the maintainer ports
them to the production source; no blind bidirectional directory mirroring is used.

The numeric base version identifies related source lines, for example production
`1.1.32` and community `1.1.32-community.1`. Community suffixes describe generic
installer/documentation revisions. They do not prove that a private device is
running that source. Existing releases remain immutable snapshots; a new commit
does not silently replace an older release archive.

Source sync, tests, firmware builds, remote pushes and actual hardware deployment
are separate results. CI never flashes a device or changes training data.

## README renders

README PNGs are off-device LVGL renders with synthetic profiles, loads and session
state. They are not photographs, captured ESP32 framebuffers or physical touch
acceptance. Native widget construction/render methods and the bundled font are
used; network, hardware and session storage are not connected. The optional
muscle-map popup is outside this documentation harness.

The workout render includes an original AI-generated squat illustration to show
what optional installer-supplied media looks like. Its [asset and generation
provenance](images/README.md) are included for reproducibility. This documentation
example does not change the adapter's runtime placeholder default or install
anything on a device.

To reproduce, provide a host-built LVGL **9.5.0** with snapshot/RGB888 support
and its matching configuration. Install `Pillow` and `freetype-py` in an isolated
development environment, then run:

```sh
python3 tools/render_readme.py \
  --lvgl-include /path/to/lvgl \
  --lvgl-library /path/to/build/lib/liblvgl.a \
  --lvgl-config /path/to/lv_conf.h
```

Review every PNG and its fixture/source provenance before committing its hash
in `docs/images/manifest.json`. The public artifact audit allows only those
specific PNG paths, hashes and dimensions and rejects metadata-bearing images.
