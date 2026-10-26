"""Decides who drives the avatar: your face, or the idle animator.

TRACKING -> face visible.
HOLD     -> face lost briefly (turned away, hand in front): freeze last pose.
AWAY     -> face lost for longer: fade into idle + microphone lip-sync.
"""

from __future__ import annotations

from enum import Enum


class Presence(Enum):
    TRACKING = "tracking"
    HOLD = "hold"
    AWAY = "away"


class PresenceMachine:
    def __init__(self, hold_s: float = 1.2, fade_s: float = 0.6) -> None:
        self.hold_s = hold_s
        self.fade_s = fade_s
        self.state = Presence.AWAY
        self.away_weight = 1.0  # 0 = fully face-driven, 1 = fully idle
        self._last_seen = float("-inf")
        self._t: float | None = None

    def update(self, has_face: bool, t: float) -> Presence:
        dt = 0.0 if self._t is None else max(t - self._t, 0.0)
        self._t = t
        if has_face:
            self._last_seen = t
            self.state = Presence.TRACKING
        elif t - self._last_seen <= self.hold_s:
            self.state = Presence.HOLD
        else:
            self.state = Presence.AWAY
        target = 1.0 if self.state is Presence.AWAY else 0.0
        step = dt / self.fade_s if self.fade_s > 0 else 1.0
        if self.away_weight < target:
            self.away_weight = min(target, self.away_weight + step)
        else:
            self.away_weight = max(target, self.away_weight - step)
        return self.state
