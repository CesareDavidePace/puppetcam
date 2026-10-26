# Changelog

## 0.1.0

First public release.

- Cartoon avatar driven by your webcam (head, eyes, brows, mouth), exposed as a virtual camera:
  works in Google Meet, Microsoft Teams, Zoom and anything else that takes a webcam.
- Runs on CPU, 100% locally. The only network access is a one-time download of the face model.
- Away mode: the avatar keeps blinking, breathing and lip-syncing to your microphone.
- Themes in TOML: colors, proportions, accessories, background.
- Small head and face movements are exaggerated by default (`--sensitivity`, default 1.5).
- `puppetcam doctor` to check your setup in one command.
- Avatars as Python plugins.
