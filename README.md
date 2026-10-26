# puppetcam

**An animated avatar for your video calls. Runs 100% locally, on CPU, with no training and no cloud.**

Camera off in a meeting feels like a black hole; camera on isn't always an option.
puppetcam turns your webcam into a cartoon that moves like you: head, eyes, brows,
mouth. Zoom, Meet, Teams and anything else just see a normal webcam.

![demo](docs/demo.gif)

- **Works everywhere:** shows up as a virtual camera, not a plugin for one app.
- **Light:** a few milliseconds of rendering per frame, no GPU needed.
- **Private:** frames and audio are processed in memory and never leave your machine.
  The only network access is a one-time download of the face model (a few MB).
- **Away mode:** step away and the avatar keeps blinking, breathing and lip-syncing
  to your microphone instead of freezing.
- **Yours:** colors, proportions, accessories and background come from a small theme file.
- **Hackable:** an avatar is one Python class. Add your own as a plugin.

> Status: alpha. Expect rough edges, and please open issues.

## Quick start

**1. Install a virtual camera backend** (one time):

| OS | What to install |
| --- | --- |
| Windows | [OBS Studio](https://obsproject.com). It ships the "OBS Virtual Camera" driver. Run it once, then quit it. |
| macOS | OBS Studio 30+. Start and stop its Virtual Camera once, allow it (see below), then quit OBS. |
| Linux | `sudo apt install v4l2loopback-dkms` then `sudo modprobe v4l2loopback devices=1 exclusive_caps=1 card_label="puppetcam"` |

**2. Install and run** (Python 3.11+):

```bash
pip install puppetcam
puppetcam doctor     # checks camera, face model, microphone and virtual camera
puppetcam
```

Look at the camera for half a second with a relaxed face while it calibrates. Then in your
meeting app pick **"OBS Virtual Camera"** (or "puppetcam" on Linux) as the camera.

> You don't need OBS open: puppetcam sends its frames into the OBS Virtual Camera itself.
> If you start the Virtual Camera from OBS, you'll see OBS's (empty) scene instead of the avatar.

Preview window keys: `q` quit · `c` recalibrate · `a` toggle away mode · `b` toggle the AVATAR badge.

### In Google Meet, Microsoft Teams and Zoom

- **Start puppetcam before joining.** If the meeting app or browser was already open and
  doesn't list the camera, restart it.
- **Meet:** Settings → Video → Camera. **Teams:** Settings → Devices → Camera.
  **Zoom:** Settings → Video → Camera.
- **Turn off background blur and virtual backgrounds** in the meeting app: they try to cut a
  person out of the cartoon. Change the background with a [theme](#themes-make-it-yours) instead.
- Your own self-view may show the AVATAR badge mirrored. Others see it the right way round.
- Small expressions too subtle? Try `puppetcam --sensitivity 2` (default 1.5), and press `c`
  to recalibrate with a relaxed face. If the avatar jitters while you're still, go down to 1.2.

### Platform notes

**Windows**
- The camera is opened with DirectShow + MJPG: it starts in well under a second, where
  Media Foundation can take several.
- Use Python 3.11 or newer: older versions sleep in ~15 ms steps on Windows, which makes the
  frame rate uneven.
- While you're away, the tracking thread switches to Windows 11 "efficiency mode" (EcoQoS).

**macOS**
- Allow the virtual camera: on macOS 26 (Tahoe) it's under **System Settings → Privacy &
  Security → Extensions → OBS → Media Extension**; on older versions under Login Items &
  Extensions → Camera Extensions. Then restart OBS once.
- Camera permission is asked for the app you launch from (Terminal, iTerm, VS Code...).
- Use a native arm64 Python on Apple Silicon (not x86 under Rosetta, which is much slower).
- Try `--gpu`: MediaPipe can run on Metal, which is faster than CPU on Apple Silicon.
- App Nap is disabled automatically, so macOS doesn't throttle puppetcam while your meeting app
  is in front.

**Linux**
- **Start puppetcam before opening the meeting in the browser.** With `exclusive_caps=1`, Chrome
  only lists the virtual camera once frames are flowing into it.
- `--gpu` works only with MediaPipe wheels built with GPU support; otherwise it falls back to CPU.

## Something doesn't work?

Run `puppetcam doctor` and paste its output into a
[new issue](https://github.com/cesaredavidepace/puppetcam/issues/new/choose). It shows your OS,
Python, camera, microphone and virtual camera status in a few lines.

## Useful options

```bash
puppetcam --size 1280x720          # output resolution (default 960x540)
puppetcam --theme office           # pick a theme (see below)
puppetcam --track-fps 15           # track at 15 Hz: about half the CPU, still smooth
puppetcam --gpu                    # try GPU tracking, falls back to CPU if unavailable
puppetcam --no-preview             # headless
puppetcam --no-vcam                # just the preview window, to try it out
puppetcam --invert-yaw             # if the avatar turns the wrong way (also pitch/roll)
puppetcam --swap-eyes              # if it winks with the wrong eye
puppetcam --sensitivity 2          # exaggerate small movements more (default 1.5, 1 = linear)
puppetcam bench --video 0          # measure tracking and render cost on your machine
puppetcam demo demo.mp4            # render a scripted clip, no webcam needed
```

## Themes: make it yours

![themes](docs/themes.png)

```bash
puppetcam themes                                  # list built-in themes
puppetcam --theme winter                          # use one
puppetcam themes --export sprout my-theme.toml    # copy the full template
puppetcam themes --check my-theme.toml            # validate your edits
puppetcam --theme my-theme.toml
```

A theme only needs what it changes. A blue sweater, glasses and your own background:

```toml
name = "Me"

[colors]
sweater = "#3B6FD4"

[accessories]
items = ["glasses"]            # sprout, glasses, beanie, headphones

[background]
image = "my-office.jpg"        # relative to this file; cropped to fill
```

Everything you can set (colors, head roundness and proportions, eye size and spacing, mouth
width, body width, accessories, background) is listed with comments in
[`themes/sprout.toml`](src/puppetcam/themes/sprout.toml). Shades like `skin_shade` are derived
automatically unless you set them. Themes cost nothing at runtime: they're applied once at startup.

## How it works

```
 webcam ──► sensor thread ─────────────────────► render loop (30 fps) ──► virtual camera
            capture 640x480                      mapping + calibration
            MediaPipe Face Landmarker            presence: tracking / hold / away
            (52 blendshapes + head pose)         idle animator + mic level
                                                 One Euro smoothing
                                                 avatar.render(params)
```

1. **Tracking:** [MediaPipe Face Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)
   gives 52 ARKit-style blendshape scores (jaw open, blink, smile...) and the head rotation.
   Pre-trained and used as-is.
2. **Mapping:** plain arithmetic turns those into 11 normalized parameters (`AvatarParams`),
   relative to your resting face captured at startup.
3. **Presence:** if your face disappears, the avatar holds its pose for a moment, then fades
   into idle animation with mouth driven by microphone loudness.
4. **Smoothing:** a [One Euro filter](https://gery.casiez.net/1euro/) removes jitter without adding lag.
5. **Rendering:** the default avatar is drawn with anti-aliased OpenCV polygons. The 3D effect
   is parallax: features slide, the far eye narrows, ears move the other way, the leaf bounces on a spring.

Performance notes and measurements: [docs/optimization.md](docs/optimization.md).

## Privacy and honesty

- No frames, audio or landmarks are saved or sent anywhere.
- The **AVATAR badge is on by default**. People in a call deserve to know they are looking at
  an avatar. You can hide it, but please tell them.

## Write your own avatar

```python
from puppetcam.avatars import Avatar
from puppetcam.params import AvatarParams

class MyAvatar(Avatar):
    name = "mine"
    def render(self, p: AvatarParams, dt: float):
        ...  # return an HxWx3 uint8 BGR image
```

Register it from your own package, no fork needed:

```toml
[project.entry-points."puppetcam.avatars"]
mine = "my_package.avatar:MyAvatar"
```

Then `puppetcam --avatar mine`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

What's coming next. Priorities follow your feedback: open an
[issue](https://github.com/cesaredavidepace/puppetcam/issues/new/choose) or a
[discussion](https://github.com/cesaredavidepace/puppetcam/discussions) to push for something.

**v0.1 — now: for people comfortable with a terminal**

- [x] Cartoon avatar as a virtual camera for Meet, Teams, Zoom and any other app
- [x] Away mode, themes, avatar plugins
- [x] `--sensitivity` for small movements, `puppetcam doctor` to check your setup

**v0.2 — no terminal needed**

- [ ] Settings saved in a file: theme, camera, sensitivity, badge. No more command-line flags
- [ ] Menu bar app (macOS) and tray app (Windows): on/off, theme, sensitivity, recalibrate,
      start at login
- [ ] One-click installers: a signed app for macOS and an installer for Windows, with the face
      model included (no download on first run)

**v0.3 — make your own character**

- [ ] Draw-your-own avatar from a few PNG layers (head, eyes, mouth shapes), no code needed
- [ ] More themes and avatars from the community

**Later**

- [ ] Own virtual camera, so OBS is no longer required (Windows 11 and macOS)
- [ ] Upper body: shoulders and hands from MediaPipe Pose Landmarker (lite)
- [ ] "Your photo" avatar: animate a single photo by mesh warping, still CPU-only
- [ ] Adaptive tracking rate (slow down when you're still, not only when away)

## License

MIT, see [LICENSE](LICENSE). The face model is downloaded from Google's MediaPipe
model storage and is not redistributed here; it is covered by its own model card and license.
