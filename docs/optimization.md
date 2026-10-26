# Performance

Goal: run all day next to a video call on an ordinary laptop, without a GPU
and without the fan spinning up. The budget per output frame at 30 fps is 33 ms;
the target is to use a small fraction of one core.

## Where the time goes

| Stage | Thread | Typical cost | Notes |
| --- | --- | --- | --- |
| Capture + decode | sensor | small at 640x480 MJPG | grows fast at 1080p |
| Face tracking | sensor | the biggest cost | measure it: `puppetcam bench --video 0` |
| Mapping, filter, presence | render | < 0.1 ms | plain arithmetic |
| Avatar render | render | ~2 ms at 960x540, ~3 ms at 1280x720 | measured on a 2-core cloud VM |
| Virtual camera send | render | ~1 ms | BGR passed straight through |

Measure on your own machine:

```bash
puppetcam bench                    # render cost at 3 output sizes
puppetcam bench --video 0          # + tracker cost on your webcam at widths 320/480/native
puppetcam --stats                  # live fps and timings every 5 s
```

## What is already done

1. **Small capture.** The camera is opened at 640x480 with MJPG and a 1-frame buffer.
   Face tracking doesn't benefit from 1080p, and decoding 1080p costs more than rendering.
2. **Grab, don't decode.** Frames we won't track are only `grab()`-ed: dequeued from the driver
   but not decoded, so the next tracked frame is fresh and cheap.
3. **Tracking off the render thread.** The render loop reads the latest observation and never waits.
4. **MediaPipe in VIDEO mode, one face.** The face detector runs only when tracking is lost;
   otherwise only the mesh model runs on the previous crop.
5. **Copy only what we use.** 52 blendshape scores and one 4x4 matrix. The 478 landmarks never
   become Python objects.
6. **Decoupled rates.** Tracking can run at 15 Hz while rendering stays at 30 fps. The One Euro
   filter is evaluated per rendered frame, so it eases between tracked samples for free.
7. **Cheap rendering.** Pre-computed background, a reused output buffer, integer sub-pixel
   polygon fills, no alpha blending, no per-frame allocations of full images.
8. **No color conversions at the end.** Frames are sent to the virtual camera as BGR, the
   format OpenCV draws in.
9. **No thread oversubscription.** `cv2.setNumThreads(1)`: our OpenCV work is tiny, so cores are
   left to MediaPipe.
10. **Away = almost idle.** When your face has been gone for a moment, tracking drops from 30 Hz
    to 4 Hz (`--away-track-fps`), just enough to notice you're back. Rendering continues.

## Per-platform

| | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Camera API | DirectShow + MJPG (MSMF opens slowly) | AVFoundation | V4L2 + MJPG |
| GPU tracking (`--gpu`) | usually not available, CPU | Metal, worth trying on Apple Silicon | only on GPU-enabled wheels |
| Power | sensor thread in EcoQoS while away (Windows 11) | App Nap disabled (`appnope`) | — |
| Timing | Python 3.11+ for high-resolution sleep | — | — |
| Gotcha | — | allow OBS "Media Extension" in Privacy & Security | start puppetcam before Chrome |

`--gpu` never fails hard: if the GPU delegate can't be created, or fails on the first frame, the
tracker reopens on CPU and logs a warning. `puppetcam bench --video 0 --gpu` shows which one ran.

## Knobs, from biggest to smallest win

| Option | Effect |
| --- | --- |
| `--track-fps 15` | roughly halves tracking CPU; motion stays smooth thanks to filtering |
| `--track-width 480` | smaller tracker input; check blendshape quality, small faces suffer |
| `--size 640x360` | cheaper render and send; meeting apps upscale anyway |
| `--fps 24` | fewer frames everywhere |

## Next ideas (good first contributions)

- **Adaptive tracking rate while present:** measure frame-to-frame motion on a tiny downscaled
  image (e.g. 32x24 absolute difference). Still face, so track at 8 Hz; movement, so 30 Hz.
- **Dirty frames:** if smoothed params barely changed, resend the previous frame instead of
  re-rendering. The virtual camera still needs a steady frame rate.
- **GPU by default on Apple Silicon** if benchmarks confirm it's consistently faster.
- **Battery preset:** `--eco` = track 12 Hz + 640x360 at 24 fps.
- **Profile, don't guess:** `python -m cProfile -o out.prof -m puppetcam --no-vcam`
  and open with `snakeviz out.prof`.

## Benchmarks to fill in

Run `puppetcam bench --video 0` and open a PR with your numbers:

| Machine | CPU | Track @480 | Track native | Render 960x540 |
| --- | --- | --- | --- | --- |
| cloud VM (2 vCPU) | — | n/a (no webcam) | n/a | 2.0 ms |
