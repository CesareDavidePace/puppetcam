"""``puppetcam doctor``: one line per thing that must work, with a hint when it doesn't.

Meant to be pasted into bug reports, so it prints versions too.
"""

from __future__ import annotations

import platform
import sys
from collections.abc import Callable

from . import __version__

OK, WARN, FAIL = "ok  ", "warn", "FAIL"


def _check_python() -> tuple[str, str]:
    if sys.platform == "darwin" and platform.machine() == "x86_64":
        import subprocess

        translated = subprocess.run(["sysctl", "-n", "sysctl.proc_translated"],
                                    capture_output=True, text=True).stdout.strip()
        if translated == "1":
            return WARN, "x86 Python under Rosetta: install a native arm64 Python, it's much faster"
    return OK, f"Python {platform.python_version()} ({platform.machine()})"


def _check_settings() -> tuple[str, str]:
    from .settings import load_settings, settings_path

    load_settings()
    path = settings_path()
    return OK, f"settings in {path}" if path.exists() else f"settings: defaults (no {path} yet)"


def _check_model() -> tuple[str, str]:
    from .tracker import ensure_model

    return OK, f"face model at {ensure_model()}"


def _check_tracker() -> tuple[str, str]:
    from .tracker import FaceTracker

    FaceTracker().close()  # loads MediaPipe's native library, which Windows may block
    return OK, "face tracker (MediaPipe) loads"


def _check_camera(index: int) -> Callable[[], tuple[str, str]]:
    def check() -> tuple[str, str]:
        from .capture import open_camera

        cap = open_camera(index, 640, 480, 30)
        try:
            for _ in range(10):  # some webcams return a few empty frames while starting
                ok, frame = cap.read()
                if ok and frame is not None:
                    h, w = frame.shape[:2]
                    return OK, f"camera {index} delivers {w}x{h} frames"
        finally:
            cap.release()
        hint = " (allow camera access for this terminal app)" if sys.platform == "darwin" else ""
        return FAIL, f"camera {index} opened but sent no frames{hint}"
    return check


def _check_mic() -> tuple[str, str]:
    from .audio import MicLevel

    MicLevel().start().stop()
    return OK, "microphone (used only for lip-sync in away mode)"


def _check_vcam() -> tuple[str, str]:
    from .sinks import VirtualCamSink

    sink = VirtualCamSink(640, 360, 30)
    name = sink.cam.device
    sink.close()
    return OK, f"virtual camera: {name}"


_HINTS = {
    "camera": "check that no other app is using the webcam, or try --camera 1",
    "microphone": "optional: puppetcam still works, away mode just won't lip-sync",
    "virtual camera": "on macOS/Windows quit OBS (its own Virtual Camera must be stopped) and retry",
}


def run_checks(camera: int = 0, vcam: bool = True) -> bool:
    print(f"puppetcam {__version__} on {platform.platform()}")
    checks: list[tuple[str, Callable[[], tuple[str, str]], bool]] = [
        ("python", _check_python, True),
        ("settings", _check_settings, True),
        ("face model", _check_model, True),
        ("face tracker", _check_tracker, True),
        ("camera", _check_camera(camera), True),
        ("microphone", _check_mic, False),
    ]
    if vcam:
        checks.append(("virtual camera", _check_vcam, True))
    healthy = True
    for name, check, required in checks:
        try:
            status, msg = check()
        except Exception as exc:  # report everything, stop at nothing
            status = FAIL if required else WARN
            lines = str(exc).strip().splitlines()
            msg = f"{name}: {lines[0]}" + "".join(f"\n       {line}" for line in lines[1:])
            if name in _HINTS:
                msg += f"\n       -> {_HINTS[name]}"
        print(f"[{status}] {msg}")
        healthy &= status != FAIL
    return healthy
