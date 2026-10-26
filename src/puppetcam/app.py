"""The live app: webcam -> tracker -> engine -> virtual camera (+ preview)."""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from .audio import try_open_mic
from .avatars.base import load_avatar
from .capture import SensorThread
from .engine import Engine
from .mapping import MappingConfig
from .platform_tweaks import disable_app_nap
from .presence import Presence
from .sinks import Pacer, PreviewWindow, VirtualCamSink
from .themes import load_theme
from .tracker import FaceTracker

log = logging.getLogger(__name__)


@dataclass
class RunConfig:
    camera: int = 0
    cam_width: int = 640
    cam_height: int = 480
    track_fps: float = 30.0
    away_track_fps: float = 4.0  # while away: just check if you're back
    gpu: bool = False
    track_width: int | None = None  # downscale before tracking (None = as captured)
    width: int = 960
    height: int = 540
    fps: int = 30
    avatar: str | None = None  # None = the avatar the theme was made for
    theme: str | None = None  # built-in theme name or path to a .toml
    badge: bool = True
    vcam: bool = True
    vcam_device: str | None = None
    vcam_backend: str | None = None
    preview: bool = True
    mic: bool = True
    model: Path | None = None
    stats: bool = False
    mapping: MappingConfig = field(default_factory=MappingConfig)


def run(cfg: RunConfig) -> None:
    cv2.setNumThreads(1)  # our OpenCV work is tiny; leave cores to MediaPipe
    disable_app_nap()  # macOS: we run behind the meeting app, don't get throttled
    theme = load_theme(cfg.theme)
    avatar = load_avatar(cfg.avatar, cfg.width, cfg.height, badge=cfg.badge, theme=theme)
    mic = try_open_mic() if cfg.mic else None
    engine = Engine(avatar, cfg.mapping, mic=mic)

    tracker = FaceTracker(cfg.model, input_width=cfg.track_width, gpu=cfg.gpu)
    sensor = SensorThread(
        tracker, cfg.camera, cfg.cam_width, cfg.cam_height,
        track_fps=cfg.track_fps, away_track_fps=cfg.away_track_fps, keep_frame=cfg.preview,
    )
    vcam = None
    if cfg.vcam:
        vcam = VirtualCamSink(cfg.width, cfg.height, cfg.fps, cfg.vcam_device, cfg.vcam_backend)
    pacer = vcam or Pacer(cfg.fps)
    preview = PreviewWindow() if cfg.preview else None

    render_ms: deque[float] = deque(maxlen=120)
    frame_times: deque[float] = deque(maxlen=120)
    last_report = time.monotonic()
    sensor.start()
    log.info("Running. Look at the camera for a moment to calibrate.")
    try:
        while True:
            if sensor.error:
                raise sensor.error
            t = time.monotonic()
            obs, cam_frame = sensor.latest()
            t0 = time.perf_counter()
            frame = engine.step(obs, t)
            render_ms.append((time.perf_counter() - t0) * 1000.0)
            st = engine.state
            sensor.set_away(st.calibrated and st.presence is Presence.AWAY)
            frame_times.append(t)
            if vcam:
                vcam.send(frame)

            fps = (len(frame_times) - 1) / (frame_times[-1] - frame_times[0]) if len(frame_times) > 1 else 0.0
            track = sum(sensor.track_ms) / len(sensor.track_ms) if sensor.track_ms else 0.0
            render = sum(render_ms) / len(render_ms)
            if preview:
                lines = [
                    f"{st.presence.value}{'' if st.calibrated else ' (calibrating)'}",
                    f"out {fps:4.1f} fps | track {track:4.1f} ms | render {render:4.1f} ms",
                ]
                key = preview.show(frame, cam_frame, lines)
                if key in (ord("q"), 27):
                    break
                if key == ord("c"):
                    engine.recalibrate()
                if key == ord("a"):
                    engine.force_away = not engine.force_away
                if key == ord("b"):
                    avatar.badge = not avatar.badge
            if cfg.stats and t - last_report > 5.0:
                last_report = t
                log.info("out %.1f fps | track %.1f ms | render %.1f ms | %s",
                         fps, track, render, engine.state.presence.value)
            pacer.wait()
    except KeyboardInterrupt:
        pass
    finally:
        sensor.stop()
        sensor.join(timeout=2.0)
        tracker.close()
        if vcam:
            vcam.close()
        if preview:
            preview.close()
        if mic:
            mic.stop()
