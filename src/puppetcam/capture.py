"""Camera + tracking in a background thread.

The render loop never waits for the camera: it always reads the most recent
observation. Frames we don't track are only ``grab()``-ed (dequeued, not
decoded), which is where most of the capture cost would otherwise go.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections import deque

import cv2
import numpy as np

from .platform_tweaks import set_current_thread_efficiency
from .tracker import FaceObservation, FaceTracker

log = logging.getLogger(__name__)


def default_backend() -> int:
    if sys.platform.startswith("win"):
        return cv2.CAP_DSHOW  # opens much faster than MSMF on most webcams
    if sys.platform == "darwin":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_V4L2


def open_camera(index: int, width: int, height: int, fps: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index, default_backend())
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)  # let OpenCV pick
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera {index}")
    # MJPG lets USB webcams deliver 30 fps at 640x480+ without saturating USB.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # avoid reading stale frames
    log.info(
        "Camera %d: %dx%d @ %.0f fps",
        index,
        cap.get(cv2.CAP_PROP_FRAME_WIDTH),
        cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
        cap.get(cv2.CAP_PROP_FPS),
    )
    return cap


class SensorThread(threading.Thread):
    def __init__(
        self,
        tracker: FaceTracker,
        camera: int = 0,
        width: int = 640,
        height: int = 480,
        camera_fps: int = 30,
        track_fps: float = 30.0,
        away_track_fps: float = 4.0,
        keep_frame: bool = False,
    ) -> None:
        super().__init__(name="puppetcam-sensor", daemon=True)
        self.tracker = tracker
        self.cap = open_camera(camera, width, height, camera_fps)
        self.active_interval = 1.0 / track_fps
        self.away_interval = 1.0 / max(min(away_track_fps, track_fps), 0.5)
        self.keep_frame = keep_frame
        self._away = False
        self._lock = threading.Lock()
        self._obs: FaceObservation | None = None
        self._frame: np.ndarray | None = None
        self._stop_event = threading.Event()
        self.track_ms: deque[float] = deque(maxlen=120)
        self.error: BaseException | None = None

    def set_away(self, away: bool) -> None:
        """While away, only check a few times per second whether you're back."""
        self._away = away

    def run(self) -> None:
        last_track = 0.0
        efficient = False
        try:
            while not self._stop_event.is_set():
                away = self._away
                if away != efficient:  # must be called from this thread
                    set_current_thread_efficiency(away)
                    efficient = away
                interval = self.away_interval if away else self.active_interval
                now = time.monotonic()
                if now - last_track < interval:
                    self.cap.grab()  # keep the driver queue fresh, skip decode
                    continue
                ok, frame = self.cap.read()
                if not ok:
                    time.sleep(0.01)
                    continue
                last_track = now
                t0 = time.perf_counter()
                obs = self.tracker.process(frame, now)
                self.track_ms.append((time.perf_counter() - t0) * 1000.0)
                with self._lock:
                    if obs is not None:
                        self._obs = obs
                    if self.keep_frame:
                        self._frame = frame
        except BaseException as exc:  # surface to the main thread
            self.error = exc
        finally:
            self.cap.release()

    def latest(self) -> tuple[FaceObservation | None, np.ndarray | None]:
        with self._lock:
            return self._obs, self._frame

    def stop(self) -> None:
        self._stop_event.set()
