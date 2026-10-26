"""The hardware-free core: observations in, frames out.

No camera, no virtual camera, no threads here, so it is fully testable and
reusable (e.g. driving the avatar from a recorded video or a network stream).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .avatars.base import Avatar
from .filters import OneEuroFilter
from .idle import IdleAnimator
from .mapping import Calibrator, MappingConfig, observation_to_params
from .params import NEUTRAL, AvatarParams, lerp
from .presence import Presence, PresenceMachine
from .tracker import FaceObservation


@dataclass
class EngineState:
    presence: Presence = Presence.AWAY
    calibrated: bool = False
    params: AvatarParams = field(default_factory=AvatarParams)


class Engine:
    def __init__(
        self,
        avatar: Avatar,
        mapping: MappingConfig | None = None,
        mic=None,
        seed: int | None = None,
    ) -> None:
        self.avatar = avatar
        self.mapping = mapping or MappingConfig()
        self.mic = mic  # anything with .mouth() -> float in 0..1
        self.calibrator = Calibrator()
        self.presence = PresenceMachine()
        self.idle = IdleAnimator(seed=seed)
        self.filter = OneEuroFilter()
        self.force_away = False
        self._face_params = NEUTRAL
        self._last_obs_t: float | None = None
        self._last_t: float | None = None
        self.state = EngineState()

    def recalibrate(self) -> None:
        self.calibrator.reset()

    def update(self, obs: FaceObservation | None, t: float) -> AvatarParams:
        """Fuse the latest observation (may be None or stale) into params."""
        fresh = obs is not None and obs.t != self._last_obs_t
        if fresh:
            self._last_obs_t = obs.t
            self.calibrator.feed(obs)
            if self.calibrator.done:
                self._face_params = observation_to_params(obs, self.calibrator.neutral, self.mapping)

        # A stale observation still counts as "face present" for a short while
        # (tracking can run slower than rendering).
        has_face = (
            not self.force_away
            and obs is not None
            and self.calibrator.done
            and (t - obs.t) < 0.5
        )
        presence = self.presence.update(has_face, t)

        mouth = self.mic.mouth() if self.mic is not None else 0.0
        idle = self.idle.sample(t, mouth_open=mouth)
        target = lerp(self._face_params, idle, self.presence.away_weight)
        target.breath = idle.breath  # always breathe

        smoothed = AvatarParams.from_array(self.filter(target.to_array(), t)).clipped()
        self.state = EngineState(presence, self.calibrator.done, smoothed)
        return smoothed

    def step(self, obs: FaceObservation | None, t: float) -> np.ndarray:
        params = self.update(obs, t)
        dt = 0.0 if self._last_t is None else t - self._last_t
        self._last_t = t
        return self.avatar.render(params, dt)
