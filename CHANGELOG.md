# Changelog


## 1.1.33-community.1 — English language support

- English (`en`) touchscreen, dialogs, muscle labels and local settings page.
- English generated workout captions and built-in catalogue names in the companion.
- Norwegian (`nb`) remains the default; user-authored names, notes and workout values are unchanged.
- Language selection during installation, with matching firmware/backend settings and isolated tests.

## 1.1.32-community.1 — initial community source preview

- Extracted the existing touchscreen/session workflow into a standalone source
  distribution with fresh history and synthetic examples.
- Added private per-installation key/config generation and self-contained Docker
  service definitions, without any runtime dependency on an assistant platform.
- DHCP and authenticated browser administration are the public defaults.
- Machine-specific cable snapping is opt-in, not inherited from one home gym.
- Replaced default restricted exercise media with original placeholder artwork;
  owned-media conversion remains an explicit local option.
- Added installation, hardware, source-build, recovery, contribution and media
  documentation, public checks and synthetic firmware CI.

Baseline workout behaviour derives from the private 1.1.32 implementation:
confirmed set entry, per-profile drafts, native OpenGym 1.4.4 prescriptions,
rest/advance feedback and retained state during short outages. A stable community
release still requires an independent clean install and physical acceptance.
