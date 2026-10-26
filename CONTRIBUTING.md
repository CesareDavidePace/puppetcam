# Contributing

Thanks for helping! Avatars, performance work and platform testing are the most
valuable contributions right now.

## Setup

```bash
git clone https://github.com/cesaredavidepace/puppetcam && cd puppetcam
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest && ruff check .
```

Tests don't need a webcam, the face model or a virtual camera. Please keep it that way:
hardware-free logic lives in `engine.py`, `mapping.py`, `filters.py`, `presence.py`, `idle.py`.

## Project layout

```
src/puppetcam/
  params.py      the 11-number contract between tracking and avatars
  tracker.py     MediaPipe wrapper -> FaceObservation
  mapping.py     blendshapes + head pose -> AvatarParams, calibration
  filters.py     One Euro smoothing
  presence.py    tracking / hold / away state machine
  idle.py        procedural blinking, breathing, gaze
  audio.py       microphone loudness -> mouth
  engine.py      fuses all of the above, no hardware
  capture.py     camera + tracker thread
  sinks.py       virtual camera, preview window, frame pacing
  themes.py      theme files: colors, proportions, accessories, background
  themes/        built-in themes (.toml), sprout.toml documents every option
  platform_tweaks.py  App Nap (macOS), EcoQoS (Windows); best-effort, never raises
  app.py         wires everything for the live app
  avatars/       Avatar base class, registry, default "sprout" avatar
  tools.py       benchmark and demo rendering
```

## Writing an avatar

1. Subclass `puppetcam.avatars.Avatar` and implement `render(params, dt)`, returning an
   HxWx3 uint8 BGR image. Reusing one buffer between calls is encouraged.
2. Read colors and options from `self.theme` (set by the base class) instead of hard-coding them,
   so users can restyle your avatar with a theme file.
3. Stay cheap: aim for under 5 ms at 1280x720 (`puppetcam bench --avatar yourname`).
4. Keep the `badge` behaviour: draw a visible "AVATAR" label when `self.badge` is true.
5. Use original designs only. No characters, logos or likenesses you don't own.
6. Ship it in this repo under `avatars/` (add it to `BUILTIN`) or as your own package via
   the `puppetcam.avatars` entry point.

## Sharing a theme

Themes are plain TOML. Add yours to `src/puppetcam/themes/` with a short name, check it with
`puppetcam themes --check`, and include a screenshot in the PR. The tests render every built-in
theme automatically.

## Pull requests

- One topic per PR, with a short description of *why*.
- Add or update tests for logic changes.
- For performance PRs, include `puppetcam bench` numbers before and after.
- Run `ruff check .` and `pytest` before pushing; CI runs both on Linux, macOS and Windows.

## Code of conduct

Be kind, assume good faith, keep feedback about the code.
