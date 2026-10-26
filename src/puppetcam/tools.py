"""Offline tools: benchmark and demo clip. No webcam needed."""

from __future__ import annotations

import math
import statistics
import time
from pathlib import Path

import cv2
import numpy as np

from .avatars.base import load_avatar
from .filters import OneEuroFilter
from .idle import IdleAnimator
from .params import AvatarParams
from .themes import load_theme


def scripted_params(t: float, idle: IdleAnimator) -> AvatarParams:
    """An 10-second performance: talk, turn, smile, surprise, tilt, nod, wink."""
    base = idle.sample(t)
    p = AvatarParams(breath=base.breath, eye_open_l=base.eye_open_l, eye_open_r=base.eye_open_r,
                     gaze_x=base.gaze_x * 0.5, gaze_y=base.gaze_y * 0.5)
    if t < 4.0:
        p.yaw = 0.85 * math.sin(2 * math.pi * t / 4.0)
        syllables = max(0.0, math.sin(2 * math.pi * 3.7 * t)) * (0.6 + 0.4 * math.sin(7.1 * t))
        p.mouth_open = syllables
    elif t < 5.2:
        p.smile = 1.0
    elif t < 6.4:
        p.brow, p.mouth_open = 1.0, 0.75
    elif t < 7.6:
        p.roll, p.smile = 0.35 * math.sin(math.pi * (t - 6.4) / 1.2), 0.4
    elif t < 8.8:
        p.pitch = 0.7 * math.sin(2 * math.pi * (t - 7.6) / 0.6)
    else:
        p.smile, p.eye_open_r = 0.8, 0.0  # wink
    return p


def render_demo(out: Path, width: int = 640, height: int = 360, fps: int = 30,
                seconds: float = 10.0, avatar: str | None = None,
                theme: str | None = None) -> list[np.ndarray]:
    av = load_avatar(avatar, width, height, badge=True, theme=load_theme(theme))
    idle, filt = IdleAnimator(seed=7), OneEuroFilter()
    frames = []
    for i in range(int(seconds * fps)):
        t = i / fps
        p = AvatarParams.from_array(filt(scripted_params(t, idle).to_array(), t)).clipped()
        frames.append(av.render(p, 1.0 / fps).copy())
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".gif":
        import imageio.v3 as iio  # optional

        rgb = [cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in frames[::2]]
        iio.imwrite(out, rgb, duration=2000 / fps, loop=0)
    else:
        writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        for f in frames:
            writer.write(f)
        writer.release()
    return frames


def _summary(ms: list[float]) -> str:
    ms = sorted(ms)
    p95 = ms[int(0.95 * (len(ms) - 1))]
    return f"mean {statistics.fmean(ms):6.2f} ms   p95 {p95:6.2f} ms"


def bench_render(sizes: list[tuple[int, int]], frames: int = 300, avatar: str | None = None,
                 theme: str | None = None) -> list[str]:
    cv2.setNumThreads(1)
    lines = []
    idle, filt = IdleAnimator(seed=1), OneEuroFilter()
    th = load_theme(theme)
    for w, h in sizes:
        av = load_avatar(avatar, w, h, theme=th)
        ms = []
        for i in range(frames):
            t = i / 30
            p = AvatarParams.from_array(filt(scripted_params(t % 10.0, idle).to_array(), t))
            t0 = time.perf_counter()
            av.render(p, 1 / 30)
            ms.append((time.perf_counter() - t0) * 1000.0)
        lines.append(f"render  {w}x{h:<5} {_summary(ms[10:])}")
    return lines


def bench_tracker(source: str, widths: list[int | None], frames: int = 150, gpu: bool = False) -> list[str]:
    """Time MediaPipe on a video file (or camera index) at several input widths."""
    from .tracker import FaceTracker

    lines = []
    for width in widths:
        cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
        tracker = FaceTracker(input_width=width, gpu=gpu)
        ms, hits = [], 0
        for i in range(frames):
            ok, frame = cap.read()
            if not ok:
                break
            t0 = time.perf_counter()
            obs = tracker.process(frame, i / 30)
            ms.append((time.perf_counter() - t0) * 1000.0)
            hits += obs is not None
        tracker.close()
        cap.release()
        label = "native" if width is None else str(width)
        if ms:
            lines.append(f"track   w={label:<6} {tracker.delegate}  {_summary(ms[5:] or ms)}"
                         f"   face in {hits}/{len(ms)}")
    return lines
