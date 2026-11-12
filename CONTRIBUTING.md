# Contributing

Use readable code with clear line breaks and small focused changes. Run
`python3 tools/check.py` before proposing a change. Firmware changes also need
the pinned synthetic compile check; do not commit your own `secrets.yaml`,
compiled provisioned firmware, private installation directory or real user data.

Preserve profile isolation, explicit set/save actions, native OpenGym calculation
parity, revision checks and retry deduplication. Do not add an administrator-token
shortcut, direct writes to mounted OpenGym state or automatic equipment commands.
Use synthetic data in tests, screenshots and bug reports.

Keep third-party notices and hash-pinned source intact. Do not add exercise media
unless its licence explicitly permits redistribution/integration here. Contributions
to covered source are licensed under this project's AGPL-3.0-or-later terms.

For a new board or OpenGym version, state the exact hardware/source and separate
what compiled, what ran, and what a human physically checked. A successful
compile does not establish physical compatibility or a stable release.
