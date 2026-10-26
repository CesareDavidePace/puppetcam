"""One Euro filter, vectorized over all avatar parameters.

Low jitter when you are still, low lag when you move fast: the cutoff
frequency grows with the speed of the signal. See Casiez et al., CHI 2012.

It is evaluated once per *rendered* frame, against the latest tracked target,
so it also hides the gap when tracking runs slower than rendering
(e.g. track at 15 Hz, render at 30 Hz) without any extra interpolation code.
"""

from __future__ import annotations

import math

import numpy as np

from .params import PARAM_NAMES

# Per-parameter tuning. Eyes and mouth must react fast (blinks last ~150 ms);
# head pose can be smoother. min_cutoff in Hz, beta is the speed coefficient.
_TUNING = {
    "yaw": (1.2, 0.6),
    "pitch": (1.2, 0.6),
    "roll": (1.2, 0.6),
    "eye_open_l": (6.0, 1.0),
    "eye_open_r": (6.0, 1.0),
    "gaze_x": (2.0, 0.5),
    "gaze_y": (2.0, 0.5),
    "mouth_open": (5.0, 1.0),
    "smile": (2.0, 0.4),
    "brow": (2.0, 0.4),
    "breath": (3.0, 0.0),
}

DEFAULT_MIN_CUTOFF = np.array([_TUNING[n][0] for n in PARAM_NAMES])
DEFAULT_BETA = np.array([_TUNING[n][1] for n in PARAM_NAMES])


def _alpha(dt: float, cutoff: np.ndarray | float) -> np.ndarray | float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    def __init__(
        self,
        min_cutoff: np.ndarray | float = DEFAULT_MIN_CUTOFF,
        beta: np.ndarray | float = DEFAULT_BETA,
        d_cutoff: float = 1.0,
    ) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self) -> None:
        self._x: np.ndarray | None = None
        self._dx: np.ndarray | None = None
        self._t = 0.0

    def __call__(self, x: np.ndarray, t: float) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        if self._x is None:
            self._x = x.copy()
            self._dx = np.zeros_like(x)
            self._t = t
            return self._x.copy()
        dt = max(t - self._t, 1e-4)
        self._t = t
        dx = (x - self._x) / dt
        self._dx = self._dx + _alpha(dt, self.d_cutoff) * (dx - self._dx)
        cutoff = self.min_cutoff + self.beta * np.abs(self._dx)
        self._x = self._x + _alpha(dt, cutoff) * (x - self._x)
        return self._x.copy()
