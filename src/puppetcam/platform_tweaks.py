"""Small OS-specific tweaks. Every function is best-effort: it never raises.

- macOS: disable App Nap, which throttles timers of apps that aren't in front
  (puppetcam always runs behind your meeting app).
- Windows: EcoQoS ("efficiency mode") for the sensor thread while you're away,
  so the slow presence check runs on efficient cores at low clocks.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

_appnope_ok = False


def disable_app_nap() -> bool:
    global _appnope_ok
    if sys.platform != "darwin":
        return False
    try:
        import appnope

        appnope.nope()
        _appnope_ok = True
        log.debug("App Nap disabled")
    except Exception as exc:
        log.warning("Could not disable App Nap (pip install appnope): %s", exc)
    return _appnope_ok


# Values from processthreadsapi.h / winnt.h
_THREAD_POWER_THROTTLING = 3  # THREAD_INFORMATION_CLASS.ThreadPowerThrottling
_THROTTLING_VERSION = 1  # THREAD_POWER_THROTTLING_CURRENT_VERSION
_EXECUTION_SPEED = 0x1  # THREAD_POWER_THROTTLING_EXECUTION_SPEED


def set_current_thread_efficiency(efficient: bool) -> bool:
    """Windows only: True = EcoQoS for the calling thread, False = normal (HighQoS).

    Only for work that doesn't affect what the user sees right now.
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class ThrottlingState(ctypes.Structure):
            _fields_ = [
                ("Version", wintypes.ULONG),
                ("ControlMask", wintypes.ULONG),
                ("StateMask", wintypes.ULONG),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThread.restype = wintypes.HANDLE
        kernel32.SetThreadInformation.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        kernel32.SetThreadInformation.restype = wintypes.BOOL
        state = ThrottlingState(
            _THROTTLING_VERSION, _EXECUTION_SPEED, _EXECUTION_SPEED if efficient else 0
        )
        ok = kernel32.SetThreadInformation(
            kernel32.GetCurrentThread(), _THREAD_POWER_THROTTLING,
            ctypes.byref(state), ctypes.sizeof(state),
        )
        if not ok:
            log.debug("SetThreadInformation failed: %d", ctypes.get_last_error())
        return bool(ok)
    except Exception as exc:
        log.debug("EcoQoS unavailable: %s", exc)
        return False
