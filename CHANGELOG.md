# Changelog

## 0.2.0

No terminal needed.

- **Menu bar app (macOS) and tray app (Windows):** turn the avatar camera on and off, pick the
  theme, sensitivity and camera, show or hide the AVATAR badge, recalibrate, switch to away mode,
  and start at login. Start it with `puppetcam tray` (or `puppetcam-tray`); on Linux it needs
  `pip install "puppetcam[tray]"`.
- **Saved settings:** theme, camera, sensitivity, badge, size and the other run options live in
  `settings.toml` in your user config folder. Flags still override it; add `--save` to keep them
  (`puppetcam --theme winter --sensitivity 2 --save`). `puppetcam settings` shows the file,
  `--edit` opens it, `--reset` removes it. The tray reads and writes the same file.
- **Installers:** `Puppetcam-0.2.0-macos-arm64.dmg` and `Puppetcam-0.2.0-windows-setup.exe`,
  built by CI on every release, with the face model included: no download on first run.
  The Windows installer needs no admin rights and can add the app to startup.
- Boolean flags now have both forms, so they can override a saved setting: `--badge`/`--no-badge`,
  `--mic`/`--no-mic`, `--gpu`/`--no-gpu`, `--invert-yaw`/`--no-invert-yaw` and so on.
- `puppetcam doctor` shows where the settings file is and uses the saved camera.

## 0.1.1

- Eyes no longer shrink when you turn your head: MediaPipe reads the far eye as half closed
  (blink score up to ~0.25) while it's open, so small blink scores are now ignored.
- Gentler 3D narrowing of the far eye (25% at full turn, was 40%).
- Windows 11: when Smart App Control blocks MediaPipe (`WinError 4551`), puppetcam explains how
  to fix it instead of crashing with a traceback.
- `puppetcam doctor` now actually loads the face tracker, so it catches that block too.
- Windows with Python 3.11/3.12: installs MediaPipe 0.10.21, which Smart App Control allows
  (tested on Windows 11 with Smart App Control on). Newer MediaPipe is still used elsewhere.

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
