# Build, flash and recover

## Source checks

Use Node 24+, Python 3.11+, g++ and FFmpeg (`ffmpeg` / `ffprobe` on PATH).
In a virtual environment, install `requirements-dev.txt`; run `npm ci --ignore-scripts`
and `python3 tools/check.py`. All fixtures are synthetic and none of these tests
contact your OpenGym server or operate a screen. Vendored upstream test files are
preserved for provenance; the panel's supported runner is `tools/check.py`.

## Firmware

Use ESPHome **2026.10.0**, pinned in `requirements-firmware.txt`. It downloads the
pinned ESP-IDF framework/toolchain on the first build; budget several GB of free
disk space. Builds use at most two compiler processes. A build host with at least
4 GB RAM is recommended. The public CI workflow uses the versioned official
ESPHome container, not a private image or credentials.

```sh
python3 -m pip install -r requirements-firmware.txt
# CI-style isolated compile, with no real network/profile credentials:
python3 tools/build_firmware.py --synthetic
```

Synthetic output is explicitly named **SYNTHETIC-NOT-FOR-INSTALL**. It is a full
compile check with matching OTA/factory/ELF and checksums, not a provisioned
release or a physical test. It never overwrites a local secrets file.

For your actual installation, provision `firmware/secrets.yaml` as described in
[INSTALL.md](INSTALL.md), then validate/compile your local wrapper:

```sh
python3 tools/build_firmware.py --entry firmware/my-gym.local.yaml
```

Alternatively compile `firmware/opengym-v3.yaml` for its DHCP/Oslo defaults. This
command does **not** upload, but its ESPHome output and binaries may contain your
private provisioning. Keep build logs, `.esphome/`, OTA/factory images and ELF
private. Never attach those to a public issue or release.

## Initial USB installation and later OTA

Preserve your original vendor recovery image/configuration before flashing. Check
the physical board revision and USB port; disconnect unrelated panels. Use the
factory image for the supported initial USB installation; OTA images are only for
compatible existing partition layouts. See the upstream hardware recovery guide
linked in [HARDWARE.md](HARDWARE.md) for board-specific USB/boot procedures.

An explicit ESPHome upload for your own configured panel can be run separately:

```sh
esphome upload firmware/my-gym.local.yaml --device /dev/ttyACM0
# Later, only after verifying the current panel address and idle state:
esphome upload firmware/my-gym.local.yaml --device YOUR_PANEL_ADDRESS
```

No script or CI job in this project uploads automatically. Avoid updating any
component while a user has an active/saving workout.

After upload, verify the **actual running version**, connection and increasing
uptime beyond the safe-mode/rollback window, then check all touch corners and the
bottom row physically. A successful uploader message alone is not proof that the
new firmware stayed installed. Optional Home Assistant diagnostics can help, but
Home Assistant is not required for training operation.

## Rollback

Retain the previous matching source, OTA, factory image and ELF before building
or replacing firmware. Restore only matching firmware on the correct hardware.
For services, retain the previous images/configs and preserve current session
records. Never overwrite later training history/drafts with an old backup to
roll back a display or companion. Resolve a pending save before stopping its
owner. USB recovery remains the fallback for a bad partition or unbootable image.

## Public source release

Commit the reviewed standalone source, then run `python3 tools/package_public.py`.
Only audited tracked source is packed with `release.json` and `SHA256SUMS`.
There are no provisioned firmware files or licensed exercise media in that package.
For a binary distribution, provide its exact corresponding source, dependency
pins, installation instructions and all required notices; never reuse a private
installation's binary.
