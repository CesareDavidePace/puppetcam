"""Face tracking with MediaPipe Face Landmarker (CPU, no training).

Outputs only what the avatar needs: 52 ARKit-style blendshape scores and the
head rotation. The 478 landmarks are computed by MediaPipe but never copied
into Python, which keeps the per-frame overhead small.
"""

from __future__ import annotations

import logging
import os
import shutil
import ssl
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


# WinError 4551: Smart App Control (Windows 11) or an App Control for Business policy
# refused to load MediaPipe's DLL, which is not code-signed.
_WIN_APP_CONTROL = 4551
APP_CONTROL_HELP = """\
Windows blocked MediaPipe's face tracking library (Smart App Control).
It ships with Google's mediapipe package and isn't code-signed. Recent versions are blocked,
older ones load fine but need Python 3.11 or 3.12:
  Easiest:     install Python 3.12 from python.org, then
                 py -3.12 -m pip install puppetcam
                 py -3.12 -m puppetcam
  Otherwise:   Windows Security > App & browser control > Smart App Control settings > Off.
               Check before turning it off: on some Windows versions it can't be turned
               back on without resetting Windows.
  Work PC:     the policy may come from your IT department; ask them to allow mediapipe."""


@dataclass
class FaceObservation:
    """One tracked frame. Angles are in degrees, raw (not calibrated)."""

    t: float
    pitch: float
    yaw: float
    roll: float
    blendshapes: dict[str, float] = field(default_factory=dict)

    def bs(self, name: str) -> float:
        return self.blendshapes.get(name, 0.0)


def default_model_path() -> Path:
    env = os.environ.get("PUPPETCAM_MODEL")
    if env:
        return Path(env)
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "puppetcam" / "face_landmarker.task"


def _ssl_context() -> ssl.SSLContext:
    """Prefer certifi's CA bundle: python.org builds on macOS ship without system certificates."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def ensure_model(path: Path | None = None, download: bool = True) -> Path:
    """Return a local model path, downloading it once (a few MB) if missing.

    This is the only network access the app ever makes.
    """
    path = Path(path) if path else default_model_path()
    if path.exists() and path.stat().st_size > 0:
        return path
    if not download:
        raise FileNotFoundError(f"Model not found at {path}. Run: puppetcam download-model")
    path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Downloading face model to %s", path)
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            with urllib.request.urlopen(MODEL_URL, timeout=60, context=_ssl_context()) as resp:
                shutil.copyfileobj(resp, tmp)
    except OSError as exc:  # URLError is an OSError
        Path(tmp.name).unlink(missing_ok=True)
        raise RuntimeError(
            f"Could not download the face model ({exc}).\n"
            f"Download it manually from\n  {MODEL_URL}\nand pass --model PATH "
            f"(or save it as {path})."
        ) from exc
    os.replace(tmp.name, path)
    return path


def rotation_to_euler_deg(rot: np.ndarray) -> tuple[float, float, float]:
    """3x3 rotation -> (pitch, yaw, roll) in degrees (x, y, z axes)."""
    angles, *_ = cv2.RQDecomp3x3(np.asarray(rot, dtype=np.float64)[:3, :3])
    pitch, yaw, roll = (float(a) for a in angles)
    return pitch, yaw, roll


class FaceTracker:
    """Thin wrapper around MediaPipe's FaceLandmarker in VIDEO mode.

    VIDEO mode matters for speed: the face detector only runs when tracking
    is lost; otherwise the mesh model is fed the previous frame's face crop.
    """

    def __init__(
        self,
        model_path: Path | None = None,
        input_width: int | None = None,
        min_confidence: float = 0.5,
        gpu: bool = False,
    ) -> None:
        os.environ.setdefault("GLOG_minloglevel", "2")  # quiet MediaPipe logs
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        model = str(ensure_model(model_path))

        def create(delegate):
            options = vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model, delegate=delegate),
                running_mode=vision.RunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=min_confidence,
                min_face_presence_confidence=min_confidence,
                min_tracking_confidence=min_confidence,
                output_face_blendshapes=True,
                output_facial_transformation_matrixes=True,
            )
            return vision.FaceLandmarker.create_from_options(options)

        self.delegate = "cpu"
        if gpu:
            # GPU availability differs per OS and per wheel build: Metal on Apple
            # Silicon, GL on some Linux builds, typically not on Windows.
            try:
                self._landmarker = create(BaseOptions.Delegate.GPU)
                self.delegate = "gpu"
            except Exception as exc:
                log.warning("GPU delegate unavailable, using CPU: %s", exc)
        if self.delegate == "cpu":
            try:
                self._landmarker = create(BaseOptions.Delegate.CPU)
            except OSError as exc:
                if getattr(exc, "winerror", None) == _WIN_APP_CONTROL:
                    raise RuntimeError(APP_CONTROL_HELP) from exc
                raise
        log.info("Face tracker running on %s", self.delegate.upper())
        self._create_cpu = lambda: create(BaseOptions.Delegate.CPU)
        self.input_width = input_width
        self._last_ts = -1

    def _prepare(self, frame_bgr: np.ndarray) -> np.ndarray:
        h, w = frame_bgr.shape[:2]
        if self.input_width and w > self.input_width:
            scale = self.input_width / w
            frame_bgr = cv2.resize(
                frame_bgr, (self.input_width, round(h * scale)), interpolation=cv2.INTER_AREA
            )
        return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    def process(self, frame_bgr: np.ndarray, t: float | None = None) -> FaceObservation | None:
        t = time.monotonic() if t is None else t
        ts = max(int(t * 1000), self._last_ts + 1)  # MediaPipe needs increasing timestamps
        self._last_ts = ts
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=self._prepare(frame_bgr))
        try:
            result = self._landmarker.detect_for_video(image, ts)
        except Exception as exc:
            if self.delegate != "gpu":
                raise
            # Some GPU setups only fail on the first inference, not at creation.
            log.warning("GPU inference failed, switching to CPU: %s", exc)
            self._landmarker.close()
            self._landmarker = self._create_cpu()
            self.delegate = "cpu"
            result = self._landmarker.detect_for_video(image, ts)
        if not result.face_blendshapes or not result.facial_transformation_matrixes:
            return None
        scores = {c.category_name: float(c.score) for c in result.face_blendshapes[0]}
        pitch, yaw, roll = rotation_to_euler_deg(result.facial_transformation_matrixes[0])
        return FaceObservation(t=t, pitch=pitch, yaw=yaw, roll=roll, blendshapes=scores)

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> FaceTracker:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
