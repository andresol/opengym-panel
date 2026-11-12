# Upstream provenance

| Material | Pin / origin | Licence notice |
| --- | --- | --- |
| OpenGym calculations/catalogue text | 1.4.4, `5f5832db56080837b58342ff50f78631dcc63e07` | `vendor/opengym/LICENSE`, `vendor/opengym/NOTICE.md` |
| MIPI/GSL3680 v3 drivers | EspControl v2.13.0, `9bf8567f1272b0b2bbe7788de95e8772620561bf` | `firmware/custom_components_v3/*/LICENSE*` |
| Muscle-map artwork | react-muscle-map / Melih Colpan | `docs/MUSCLEMAP-LICENSE.txt` |
| DejaVu Sans | bundled font | `firmware/fonts/LICENSE.txt` |

The 234 OpenGym runtime/metadata files listed in `upstream-1.4.4-sha256.json`
remain byte-for-byte pinned. `tests/opengym-144.test.mjs` verifies them. Native
prescriptions use upstream `effectiveRoutines`, `buildSessionEntries`, warmup,
progression, programme-date and selected-gym semantics, rather than an independent
training algorithm. Update this pin deliberately and rerun parity tests.

The public companion's own source is AGPL-3.0-or-later. Original runtime/Python
driver notices are retained; ESPHome uses GPLv3 for runtime C++ and MIT for Python.
The full upstream notice is included to preserve exercise-text and other notices;
it does not mean every optional asset/package mentioned in it is included here.

No OpenGym installation files, accounts, history, paired tokens or exercise media
are copied by the installer. The upstream text catalogue and alias metadata are
public source. Gym visual assets are excluded; see [MEDIA.md](MEDIA.md).
