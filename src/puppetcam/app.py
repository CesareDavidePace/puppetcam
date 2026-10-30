"""The live app: webcam -> tracker -> engine -> virtual camera (+ preview)."""

from __future__ import annotations

import logging
import threading
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
from .settings import Settings
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

    @classmethod
    def from_settings(cls, s: Settings, **overrides) -> RunConfig:
        width, height = s.width_height
        cfg = cls(
            camera=s.camera, track_fps=s.track_fps, gpu=s.gpu,
            width=width, height=height, fps=s.fps,
            avatar=s.avatar or None, theme=s.theme, badge=s.badge, mic=s.mic,
            mapping=MappingConfig(invert_yaw=s.invert_yaw, invert_pitch=s.invert_pitch,
                                  invert_roll=s.invert_roll, swap_eyes=s.swap_eyes,
                                  sensitivity=s.sensitivity),
        )
        for k, v in overrides.items():
            setattr(cfg, k, v)
        return cfg


class Session:
    """Everything that runs while the avatar camera is on.

    Built on the calling thread (on macOS the camera permission prompt needs the
    main thread), then ``run()`` loops until ``stop`` is set or the preview is closed.
    The setters may be called from another thread while it runs.
    """

    def __init__(self, cfg: RunConfig) -> None:
        cv2.setNumThreads(1)  # our OpenCV work is tiny; leave cores to MediaPipe
        disable_app_nap()  # macOS: we run behind the meeting app, don't get throttled
        self.cfg = cfg
        self.avatar = load_avatar(cfg.avatar, cfg.width, cfg.height, badge=cfg.badge,
                                  theme=load_theme(cfg.theme))
        self.mic = None
        self.tracker = None
        self.sensor = None
        self.vcam = None
        self.preview = None
        try:
            self.mic = try_open_mic() if cfg.mic else None
            self.engine = Engine(self.avatar, cfg.mapping, mic=self.mic)
            self.tracker = FaceTracker(cfg.model, input_width=cfg.track_width, gpu=cfg.gpu)
            self.sensor = SensorThread(
                self.tracker, cfg.camera, cfg.cam_width, cfg.cam_height,
                track_fps=cfg.track_fps, away_track_fps=cfg.away_track_fps, keep_frame=cfg.preview,
            )
            if cfg.vcam:
                self.vcam = VirtualCamSink(cfg.width, cfg.height, cfg.fps,
                                           cfg.vcam_device, cfg.vcam_backend)
        except BaseException:
            self.close()
            raise

    # -- live controls
    def recalibrate(self) -> None:
        self.engine.recalibrate()

    def set_away(self, away: bool) -> None:
        self.engine.force_away = away

    def set_badge(self, badge: bool) -> None:
        self.avatar.badge = badge

    def set_sensitivity(self, sensitivity: float) -> None:
        self.engine.mapping.sensitivity = sensitivity

    def set_theme(self, spec: str | None) -> None:
        """Swap the theme between two frames (themes are applied when the avatar is built)."""
        avatar = load_avatar(self.cfg.avatar, self.cfg.width, self.cfg.height,
                             badge=self.avatar.badge, theme=load_theme(spec))
        self.avatar = avatar
        self.engine.avatar = avatar

    @property
    def presence(self) -> Presence:
        return self.engine.state.presence

    def run(self, stop: threading.Event | None = None) -> None:
        cfg, engine, sensor, vcam = self.cfg, self.engine, self.sensor, self.vcam
        pacer = vcam or Pacer(cfg.fps)
        if cfg.preview and self.preview is None:
            self.preview = PreviewWindow()
        preview = self.preview

        render_ms: deque[float] = deque(maxlen=120)
        frame_times: deque[float] = deque(maxlen=120)
        last_report = time.monotonic()
        sensor.start()
        log.info("Running. Look at the camera for a moment to calibrate.")
        while stop is None or not stop.is_set():
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
                    self.recalibrate()
                if key == ord("a"):
                    self.set_away(not engine.force_away)
                if key == ord("b"):
                    self.set_badge(not self.avatar.badge)
            if cfg.stats and t - last_report > 5.0:
                last_report = t
                log.info("out %.1f fps | track %.1f ms | render %.1f ms | %s",
                         fps, track, render, engine.state.presence.value)
            pacer.wait()

    def close(self) -> None:
        if self.sensor:
            self.sensor.stop()
            if self.sensor.is_alive():
                self.sensor.join(timeout=2.0)
            else:
                self.sensor.cap.release()  # never started: run() would have released it
        if self.tracker:
            self.tracker.close()
        if self.vcam:
            self.vcam.close()
        if self.preview:
            self.preview.close()
        if self.mic:
            self.mic.stop()
        self.sensor = self.tracker = self.vcam = self.preview = self.mic = None


def run(cfg: RunConfig) -> None:
    session = Session(cfg)
    try:
        session.run()
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
