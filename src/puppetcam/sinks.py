"""Where frames go: a virtual webcam, a preview window, or nowhere."""

from __future__ import annotations

import logging
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)

VCAM_HELP = """\
No virtual camera backend found. Install one:
  Windows : OBS Studio (provides 'OBS Virtual Camera'), then run once and close it
  macOS   : OBS Studio 30+, start its Virtual Camera once so macOS registers it
  Linux   : sudo apt install v4l2loopback-dkms
            sudo modprobe v4l2loopback devices=1 exclusive_caps=1 card_label="Puppetcam"
"""


class VirtualCamSink:
    def __init__(self, width: int, height: int, fps: int,
                 device: str | None = None, backend: str | None = None) -> None:
        import pyvirtualcam

        try:
            self.cam = pyvirtualcam.Camera(
                width=width, height=height, fps=fps,
                fmt=pyvirtualcam.PixelFormat.BGR,  # what OpenCV draws: no conversion
                device=device, backend=backend, print_fps=False,
            )
        except RuntimeError as exc:
            raise RuntimeError(f"{exc}\n\n{VCAM_HELP}") from exc
        log.info("Virtual camera: %s", self.cam.device)

    def send(self, frame: np.ndarray) -> None:
        self.cam.send(frame)

    def wait(self) -> None:
        self.cam.sleep_until_next_frame()

    def close(self) -> None:
        self.cam.close()


class Pacer:
    """Fixed-rate loop timing when no virtual camera paces us."""

    def __init__(self, fps: int) -> None:
        self.period = 1.0 / fps
        self._next = time.perf_counter()

    def wait(self) -> None:
        self._next += self.period
        delay = self._next - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        else:
            self._next = time.perf_counter()  # we're late: don't try to catch up


class PreviewWindow:
    TITLE = "puppetcam  [q] quit  [c] recalibrate  [a] away  [b] badge"

    def __init__(self, scale: float = 0.75) -> None:
        self.scale = scale
        cv2.namedWindow(self.TITLE, cv2.WINDOW_AUTOSIZE)

    def show(self, frame: np.ndarray, camera: np.ndarray | None, lines: list[str]) -> int:
        view = frame
        if self.scale != 1.0:
            view = cv2.resize(frame, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA)
        else:
            view = frame.copy()
        if camera is not None:  # mirrored self-view thumbnail, top-right
            th = view.shape[0] // 4
            tw = round(camera.shape[1] * th / camera.shape[0])
            thumb = cv2.flip(cv2.resize(camera, (tw, th), interpolation=cv2.INTER_AREA), 1)
            view[8 : 8 + th, -tw - 8 : -8] = thumb
        for i, line in enumerate(lines):
            cv2.putText(view, line, (10, 22 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (255, 255, 255), 1, cv2.LINE_AA)
        cv2.imshow(self.TITLE, view)
        return cv2.waitKey(1) & 0xFF

    def close(self) -> None:
        cv2.destroyWindow(self.TITLE)
