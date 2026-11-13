# Interface languages

The native panel supports English (`en`) and Norwegian Bokmål (`nb`). English
is the default for new community installations; the private edition keeps
Norwegian. Existing explicit language settings are never migrated automatically.
The same choice is used for the touchscreen, its local settings page and the
session companion's generated workout text.

The language is an installation setting, not a touchscreen toggle. Changing it
requires rebuilding the panel firmware and updating the session companion's
environment. It does not change OpenGym's own language setting or your units.

## New installation

In the community checkout, use the `tools/setup.py` command
in the [installation guide](https://github.com/andresol/opengym-panel/blob/main/docs/INSTALL.md). Setup writes the chosen language to the
companion's `PANEL_LANGUAGE` environment and to the generated private
`installation.json`.

Use that file to generate the matching firmware wrapper:

```sh
python3 tools/configure_installation.py \
  --config /srv/opengym-panel/installation.json --name my-gym
```

Build `firmware/my-gym.local.yaml` using your private provisioning. Community
setup selects English when no language option is supplied. Use `--language nb`
for Norwegian.

## Existing installation

Set `locale.language` to `en` in your private installation configuration and
generate a new local wrapper. Set `PANEL_LANGUAGE=en` for the **session
companion** as well. Keep the timezone, profile bindings, credentials and media
configuration unchanged. Rebuild and install through the normal update process
when no workout is active; the configuration tool does not deploy anything.

## What is translated

Buttons, weekdays, dialogs, connection/save messages, muscle labels, set progress,
numeric captions and the local web settings page follow the selected language.
The session companion also translates its rest, warm-up and load descriptions.
Built-in exercises use the English upstream catalogue names in English mode;
Norwegian keeps the existing display-name aliases.

Profile names, routine names, custom exercise names and your notes are kept as
written. Existing workouts, prescriptions, results, unit choices and pairing
are not rewritten. English displays decimal points; Norwegian displays commas.

## Offline checks

```sh
node --test tests/language.test.mjs tests/configuration.test.mjs
python3 -m unittest discover -s tests/native -p test_language.py -v
```

The community builder can compile either language with synthetic credentials:

```sh
python3 tools/build_firmware.py --synthetic --language en
```

These checks neither operate a physical panel nor prove its touch acceptance.
