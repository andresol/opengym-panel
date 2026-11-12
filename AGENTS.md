# Community source development

Use readable code, synthetic fixtures and the pinned upstream sources. Run
`python3 tools/check.py`. A firmware change also requires the synthetic full
compile. No automatic deployment or hardware actions belong in source checks.

This edition and the maintainer's private installation share one development
workflow; see `docs/DEVELOPMENT.md`. Do not merge private history or copy private
configuration/firmware into this repository. The generic installer, authenticated
admin, DHCP and placeholder-media defaults must remain suitable for a fresh user.

README must depict the authentic native interface. Andre clarified on
12 November 2026 that he wants clean LVGL renders with fictional profile/workout
values and the original exercise artwork as displayed, NOT his installation
photo, AI art or a placeholder posing as the finished interface. This supersedes
the earlier interpretation that his photo should be published. Label desktop
renders honestly; they are not captured ESP32 framebuffers. Strip metadata and
hash-approve each documentation image. Preserve separate rights notices for
visible third-party artwork without claiming a screenshot exemption or shipping
standalone reusable exercise assets. No real profiles, records, passwords,
configuration or provisioning are authorized by this documentation request.
