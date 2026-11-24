# Changelog

## 0.2.1

Fixes from the first Linux report ([#1](https://github.com/cesaredavidepace/puppetcam/issues/1)),
and Linux without the fiddly parts.

- **Up/down head movement is no longer reversed.** MediaPipe's head pitch is positive when the chin
  goes down; the avatar's is positive when you look up. This affected every OS. If you saved
  `invert_pitch = true` as a workaround, remove it: `puppetcam --no-invert-pitch --save`.
- **`puppetcam setup` (Linux):** one command, one password prompt. Installs `v4l2loopback` if it's
  missing (apt-based distros; others get the exact command), keeps the virtual camera after reboots
  and adds Puppetcam to the applications menu. `--dry-run` shows the root commands.
- Linux: Qt dialogs of the preview window show their text again. Some OpenCV wheels (4.13, 5.0)
  ship Qt without fonts; puppetcam now points Qt at the system fonts. The preview window also
  drops Qt's toolbar and status bar.
- Closing the preview window with its close button quits, like `q` (on Linux, Qt reopened it).
- The tray app is installed on Linux too (no more `[tray]` extra); when the virtual camera is
  missing, its first menu line offers to set it up.
- `puppetcam doctor` warns when the Linux virtual camera won't survive a reboot.

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
