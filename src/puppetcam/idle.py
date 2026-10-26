"""Procedural "alive" motion for when you are away from the camera.

Natural-looking idle is mostly three things: blinks at irregular intervals,
gaze that jumps (saccades) instead of drifting, and slow layered sway.
"""

from __future__ import annotations

import math
import random

from .params import AvatarParams

BLINK_DURATION = 0.16  # seconds, close + open


class IdleAnimator:
    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._next_blink = self._rng.uniform(1.0, 3.0)
        self._blink_start = -1.0
        self._next_saccade = 0.0
        self._gaze = (0.0, 0.0)

    def breath(self, t: float) -> float:
        return 0.5 + 0.5 * math.sin(2.0 * math.pi * 0.23 * t)

    def _blink(self, t: float) -> float:
        """Returns eye openness 0..1."""
        if t >= self._next_blink:
            self._blink_start = t
            # Occasionally a quick double blink, like people do.
            gap = 0.25 if self._rng.random() < 0.15 else self._rng.uniform(2.5, 6.0)
            self._next_blink = t + gap
        phase = (t - self._blink_start) / BLINK_DURATION
        if 0.0 <= phase <= 1.0:
            return abs(1.0 - 2.0 * phase)
        return 1.0

    def sample(self, t: float, mouth_open: float = 0.0) -> AvatarParams:
        if t >= self._next_saccade:
            self._gaze = (self._rng.uniform(-0.5, 0.5), self._rng.uniform(-0.3, 0.3))
            self._next_saccade = t + self._rng.uniform(0.8, 3.5)
        eye = self._blink(t)
        tau = 2.0 * math.pi
        return AvatarParams(
            yaw=0.10 * math.sin(tau * 0.07 * t) + 0.05 * math.sin(tau * 0.19 * t + 1.3),
            pitch=0.05 * math.sin(tau * 0.11 * t + 0.4),
            roll=0.04 * math.sin(tau * 0.09 * t + 2.1),
            eye_open_l=eye,
            eye_open_r=eye,
            gaze_x=self._gaze[0],
            gaze_y=self._gaze[1],
            mouth_open=mouth_open,
            smile=0.15,
            brow=0.05 * math.sin(tau * 0.05 * t),
            breath=self.breath(t),
        )
