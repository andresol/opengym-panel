# Install your own panel

## 1. Prerequisites and profile binding

Use the exact [supported hardware](HARDWARE.md), a functioning OpenGym 1.4.4
installation and a Linux Docker host on the same trusted LAN as the panel.
Back up your OpenGym data and preserve the panel's original USB recovery image.

Copy `config/profiles.example.json` to a **private path outside this repository**.
Replace the placeholder UID with the existing user's OpenGym ID. An operator
can identify it from the user's `state-<UID>.json` filename on the OpenGym host;
do not print or share the file's content. The slug is a local non-secret label,
not the OpenGym UID. Use separate entries for separate people. Consent and local
access to someone's data are your responsibility. Never bind an administrator.
The pairing service rejects a code issued for a different UID or an admin.

## 2. Generate a private installation

Example only: `192.0.2.10` is a documentation address; use your host's real LAN
address. The API URL must be reachable **from the Docker session container**, not
only from the browser. With OpenGym published on host port 8888, Linux Docker's
`host.docker.internal` mapping works; otherwise choose its actual API origin.

```sh
python3 tools/setup.py \
  --profiles /srv/private/panel-profiles.json \
  --data-dir /srv/opengym/data \
  --api-url http://host.docker.internal:8888 \
  --panel-url http://192.0.2.10:8893 \
  --bind-address 192.0.2.10 \
  --language nb \
  --output /srv/opengym-panel \
  --uid 1000 --gid 1000
```

Run this in your source checkout **on the companion host**; generated build
contexts point to that checkout. It does not send data or start anything.
It creates mode-0600 service configs, a fresh ESPHome secrets file, a Compose
file and an `installation.json` with matching language/timezone settings. Choose
`--language en` for English, or `nb` (the default) for Norwegian Bokmål.
The output directory must not already exist. Running as root assigns the
new files to the selected non-root UID/GID; without root use your own UID/GID.
Nothing changes ownership or permissions in OpenGym's data directory.

The chosen service UID must already be able to read the selected state files
through the read-only mount. Arrange narrowly scoped read access if necessary;
do not make the entire OpenGym directory world-readable. The companion's own
`sessions/` directory is the only writable application mount.

## 3. Start the companions

```sh
docker compose -f /srv/opengym-panel/compose.yaml config --quiet
docker compose -f /srv/opengym-panel/compose.yaml up -d --build
docker compose -f /srv/opengym-panel/compose.yaml ps
curl --fail http://192.0.2.10:8893/health
```

Only adapter port 8893 is published, on the explicitly selected LAN address.
Port 8894 stays internal. Host API access must match your existing OpenGym setup.
Keep this network private: HTTP bearer tokens are not protected from a LAN
observer. Use an isolated trusted network/VPN; do not publish either companion
through a public proxy. There is no requirement to expose a server on the internet.

The health endpoint proves the process is running, not that profile reading,
pairing or workout saving works. Verify all three separately during acceptance.

## 4. Provision and build the screen

Edit only the two Wi-Fi placeholders in the generated `secrets.yaml`. The other
values are already unique and match the companions. Copy it privately to
`firmware/secrets.yaml` in your checkout; it is Git-ignored and excluded from the
Docker build context. The file also holds your browser-admin password.

The base firmware uses DHCP, Europe/Oslo time and Norwegian. Generate a wrapper
from setup's private `installation.json` to use the same language and timezone
as the companion. For additional device/network choices, use a private copy of
`config/installation.example.json`:

```sh
python3 tools/configure_installation.py --config /srv/opengym-panel/installation.json --name my-gym
```

`firmware/my-gym.local.yaml` includes the supported application. Static mode
requires a valid address, subnet, gateway and DNS; DHCP is the default. Set the
**same timezone and language** in setup and the firmware wrapper. `nb` and `en`
are supported; see [languages](LANGUAGES.md).
Use [the build guide](BUILDING.md) to validate/compile that exact entry.

## 5. Pair and accept

Choose your person on the screen. In the same person's OpenGym account, create
a code under **Settings → Pair the mobile app** and enter it on the panel. Do
not copy coach/admin tokens into configs or mint an authentication token yourself.

Before normal use, check all touch corners, lowest controls, profile isolation,
the opening set targets versus the phone, explicit set logging, rest timing and
one saved **real intended** workout. Verify that it appears once in the right
OpenGym profile. Do not use someone else's training history for a test.

Open `http://<panel-address>/admin` with the generated admin username/password.
Record first-boot health, actual firmware version and increasing uptime. Physical
acceptance is separate from compilation and backend test success.

## Optional cable label table

By default loads/steps come from native OpenGym calculations without a special
machine override. To opt in, add `PANEL_CABLE_WEIGHTS_KG` to **sessions.environment**
in your private generated Compose file: a JSON string such as `[0,5,10,15,20]`.
The list supports at most 24 choices to fit the current touchscreen grid. It must start at zero and contain strictly increasing numeric kg labels.
It applies to cable exercises in kg profiles on this installation; lb and other
equipment are not converted. Use the actual printed stack labels, not assumed
pulley force. Existing drafts/history and routines are not rewritten. An averaged
nominal step drives prospective progression, then the explicit labels select the
nearest load. If your cable machines differ, leave this installation-wide option
off and use ordinary OpenGym settings/manual load entry.

## Updates and removal

Keep the source, previous firmware, private configs and session store separately
backed up. Never update while any user has an active or saving panel session.
Build/test a pinned new source version, then recreate only these two companions.
Do not restore old OpenGym data just to remove/roll back this companion.

```sh
docker compose -f /srv/opengym-panel/compose.yaml down
```

This removes only the companion containers/network. Preserve the private session
directory until its drafts, pending saves and tokens are deliberately retired.
