"""Turns raw tracking (blendshapes + head angles) into AvatarParams.

Everything here is plain arithmetic: thresholds, ranges and a per-user
neutral pose captured during calibration. No learned model is involved.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .params import AvatarParams
from .tracker import FaceObservation


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def _boost(x: float, sensitivity: float) -> float:
    """Response curve for a value in [-1, 1]: above 1, small movements grow, extremes stay put."""
    if sensitivity == 1.0:
        return x
    return float(np.copysign(abs(x) ** (1.0 / sensitivity), x))


def _wrap_deg(a: float) -> float:
    """Wrap an angle difference into [-180, 180)."""
    return (a + 180.0) % 360.0 - 180.0


@dataclass
class MappingConfig:
    yaw_range_deg: float = 35.0
    pitch_range_deg: float = 25.0
    invert_yaw: bool = False
    invert_pitch: bool = False
    invert_roll: bool = False
    swap_eyes: bool = False  # flip if the avatar winks with the wrong eye
    blink_closed: float = 0.55  # eyeBlink score at which the eye counts as closed
    # eyeBlink rises to ~0.25 on the far eye when you turn your head, or when you look down,
    # with the eye still open. Up to this much above rest, the eye stays fully open.
    blink_deadzone: float = 0.25
    jaw_full_open: float = 0.45  # jawOpen score mapped to mouth_open = 1
    smile_gain: float = 1.6
    brow_gain: float = 1.8
    gaze_gain: float = 1.4
    sensitivity: float = 1.5  # >1 exaggerates small head and face movements, 1 = linear


@dataclass
class Neutral:
    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0
    blink_l: float = 0.0
    blink_r: float = 0.0
    jaw: float = 0.0
    smile: float = 0.0
    brow: float = 0.0


class Calibrator:
    """Averages the first N tracked frames to learn the user's resting face.

    "Learn" here is just an average: no training, done in about half a second.
    """

    def __init__(self, samples: int = 15) -> None:
        self.samples = samples
        self.reset()

    def reset(self) -> None:
        self._acc: list[np.ndarray] = []
        self.neutral = Neutral()
        self.done = False

    def feed(self, obs: FaceObservation) -> None:
        if self.done:
            return
        self._acc.append(np.array(_raw_features(obs)))
        if len(self._acc) >= self.samples:
            data = np.stack(self._acc)
            mean = data.mean(axis=0)
            # Average angles around the first sample so +-180 wrap-around is safe.
            ref = data[0, :3]
            mean[:3] = ref + np.array(
                [np.mean([_wrap_deg(v - ref[i]) for v in data[:, i]]) for i in range(3)]
            )
            self.neutral = Neutral(*(float(v) for v in mean))
            self.done = True


def _raw_features(obs: FaceObservation) -> tuple[float, ...]:
    return (
        obs.pitch,
        obs.yaw,
        obs.roll,
        obs.bs("eyeBlinkRight"),  # subject's right eye = viewer's left
        obs.bs("eyeBlinkLeft"),
        obs.bs("jawOpen"),
        _smile_raw(obs),
        _brow_raw(obs),
    )


def _smile_raw(obs: FaceObservation) -> float:
    smile = 0.5 * (obs.bs("mouthSmileLeft") + obs.bs("mouthSmileRight"))
    frown = 0.5 * (obs.bs("mouthFrownLeft") + obs.bs("mouthFrownRight"))
    return smile - frown


def _brow_raw(obs: FaceObservation) -> float:
    up = 0.5 * obs.bs("browInnerUp") + 0.25 * (
        obs.bs("browOuterUpLeft") + obs.bs("browOuterUpRight")
    )
    down = 0.5 * (obs.bs("browDownLeft") + obs.bs("browDownRight"))
    return up - down


def observation_to_params(
    obs: FaceObservation, neutral: Neutral, cfg: MappingConfig
) -> AvatarParams:
    yaw = _wrap_deg(obs.yaw - neutral.yaw) / cfg.yaw_range_deg
    pitch = _wrap_deg(obs.pitch - neutral.pitch) / cfg.pitch_range_deg
    roll = np.deg2rad(_wrap_deg(obs.roll - neutral.roll))
    if cfg.invert_yaw:
        yaw = -yaw
    if cfg.invert_pitch:
        pitch = -pitch
    if cfg.invert_roll:
        roll = -roll

    def eye_open(blink: float, base: float) -> float:
        start = base + cfg.blink_deadzone
        span = max(cfg.blink_closed - start, 0.1)
        return 1.0 - _clamp((blink - start) / span)

    eye_l = eye_open(obs.bs("eyeBlinkRight"), neutral.blink_l)
    eye_r = eye_open(obs.bs("eyeBlinkLeft"), neutral.blink_r)
    if cfg.swap_eyes:
        eye_l, eye_r = eye_r, eye_l

    # Gaze: average both eyes. Subject's "out" on the left eye = viewer's right.
    look_right = 0.5 * (obs.bs("eyeLookOutLeft") + obs.bs("eyeLookInRight"))
    look_left = 0.5 * (obs.bs("eyeLookOutRight") + obs.bs("eyeLookInLeft"))
    look_up = 0.5 * (obs.bs("eyeLookUpLeft") + obs.bs("eyeLookUpRight"))
    look_down = 0.5 * (obs.bs("eyeLookDownLeft") + obs.bs("eyeLookDownRight"))

    mouth = _clamp((obs.bs("jawOpen") - neutral.jaw) / cfg.jaw_full_open)
    smile = _clamp((_smile_raw(obs) - neutral.smile) * cfg.smile_gain, -1.0, 1.0)
    brow = _clamp((_brow_raw(obs) - neutral.brow) * cfg.brow_gain, -1.0, 1.0)

    s = cfg.sensitivity
    return AvatarParams(
        yaw=_boost(_clamp(yaw, -1.0, 1.0), s),
        pitch=_boost(_clamp(pitch, -1.0, 1.0), s),
        roll=_clamp(float(roll), -0.8, 0.8),
        eye_open_l=eye_l,
        eye_open_r=eye_r,
        gaze_x=_boost(_clamp((look_right - look_left) * cfg.gaze_gain, -1.0, 1.0), s),
        gaze_y=_boost(_clamp((look_up - look_down) * cfg.gaze_gain, -1.0, 1.0), s),
        mouth_open=_boost(mouth, s),
        smile=_boost(smile, s),
        brow=_boost(brow, s),
    )
