# Security

This project is intended for a trusted LAN or VPN. It is not an internet-facing
service. Distinct adapter-read, internal-read, workout-write, API, OTA and admin
credentials are generated locally. HTTP service keys require a trusted network.

Report suspected vulnerabilities privately to the repository maintainer before
opening a public issue. Include versions, a minimal synthetic reproduction and
the failing boundary. Do not send tokens, profile IDs, training state, personal
photos, `secrets.yaml`, provisioned firmware or entire diagnostic archives.

Only the current community preview is under development. No long-term support,
security audit or compatibility with arbitrary hardware/OpenGym versions is claimed.
