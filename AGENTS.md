# Community source development

Use readable code, synthetic fixtures and the pinned upstream sources. Run
`python3 tools/check.py`. A firmware change also requires the synthetic full
compile. No automatic deployment or hardware actions belong in source checks.

This edition and the maintainer's private installation share one development
workflow; see `docs/DEVELOPMENT.md`. Do not merge private history or copy private
configuration/firmware into this repository. The generic installer, authenticated
admin, DHCP and placeholder-media defaults must remain suitable for a fresh user.

README images must be generated from synthetic fixtures, clearly labelled as
desktop renders, stripped of metadata and individually hash-approved by the
public audit. Never use real profile IDs, passwords, workouts or restricted
exercise artwork in screenshots. No new binary asset is implicitly approved.
