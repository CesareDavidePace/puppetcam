"""The small, normalized vector that drives every avatar.

Everything upstream (tracking, idle animation, microphone) produces an
``AvatarParams``; everything downstream (avatars) only consumes one. Keeping
this contract tiny is what lets avatars be swapped and written by anyone.

Conventions are in *image space*, as seen by the viewer of the video:
``yaw > 0`` means the face turns toward the viewer's right, ``*_l`` means the
eye on the viewer's left.
"""

from __future__ import annotations

from dataclasses import astuple, dataclass, fields

import numpy as np


@dataclass
class AvatarParams:
    yaw: float = 0.0  # -1..1, roughly +-35 degrees of head turn
    pitch: float = 0.0  # -1 (looking down) .. 1 (looking up)
    roll: float = 0.0  # radians, positive = clockwise on screen
    eye_open_l: float = 1.0  # 0 closed .. 1 open
    eye_open_r: float = 1.0
    gaze_x: float = 0.0  # -1..1
    gaze_y: float = 0.0  # -1 (down) .. 1 (up)
    mouth_open: float = 0.0  # 0..1
    smile: float = 0.0  # -1 (frown) .. 1 (smile)
    brow: float = 0.0  # -1 (frown) .. 1 (raised)
    breath: float = 0.0  # 0..1, slow body motion

    def to_array(self) -> np.ndarray:
        return np.asarray(astuple(self), dtype=np.float64)

    @classmethod
    def from_array(cls, values: np.ndarray) -> AvatarParams:
        return cls(*(float(v) for v in values))

    def clipped(self) -> AvatarParams:
        return AvatarParams.from_array(np.clip(self.to_array(), LOWER, UPPER))


PARAM_NAMES: tuple[str, ...] = tuple(f.name for f in fields(AvatarParams))
NEUTRAL = AvatarParams()

LOWER = np.array([-1, -1, -0.8, 0, 0, -1, -1, 0, -1, -1, 0], dtype=np.float64)
UPPER = np.array([1, 1, 0.8, 1, 1, 1, 1, 1, 1, 1, 1], dtype=np.float64)


def lerp(a: AvatarParams, b: AvatarParams, t: float) -> AvatarParams:
    """Linear blend, t=0 -> a, t=1 -> b."""
    t = float(np.clip(t, 0.0, 1.0))
    return AvatarParams.from_array(a.to_array() * (1.0 - t) + b.to_array() * t)
