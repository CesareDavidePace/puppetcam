"""Tests for everything that doesn't need a webcam or the face model."""

from __future__ import annotations

import math

import numpy as np
import pytest

from puppetcam.avatars import available_avatars, load_avatar
from puppetcam.engine import Engine
from puppetcam.filters import OneEuroFilter
from puppetcam.idle import IdleAnimator
from puppetcam.mapping import Calibrator, MappingConfig, Neutral, observation_to_params
from puppetcam.params import PARAM_NAMES, AvatarParams, lerp
from puppetcam.presence import Presence, PresenceMachine
from puppetcam.tracker import FaceObservation, rotation_to_euler_deg


def obs(t=0.0, pitch=0.0, yaw=0.0, roll=0.0, **bs) -> FaceObservation:
    return FaceObservation(t=t, pitch=pitch, yaw=yaw, roll=roll, blendshapes=bs)


# ------------------------------------------------------------------ params
def test_params_roundtrip_and_lerp():
    p = AvatarParams(yaw=0.5, mouth_open=1.0)
    assert AvatarParams.from_array(p.to_array()) == p
    mid = lerp(AvatarParams(), p, 0.5)
    assert mid.yaw == pytest.approx(0.25) and mid.mouth_open == pytest.approx(0.5)
    assert len(PARAM_NAMES) == len(p.to_array())


def test_clipped_keeps_ranges():
    p = AvatarParams(yaw=5, mouth_open=-1, eye_open_l=3).clipped()
    assert p.yaw == 1 and p.mouth_open == 0 and p.eye_open_l == 1


# ----------------------------------------------------------------- filters
def test_one_euro_converges_and_smooths():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0)
    f(np.zeros(3), 0.0)
    out = None
    for i in range(1, 200):
        out = f(np.ones(3), i / 30)
    assert np.allclose(out, 1.0, atol=1e-3)
    f.reset()
    f(np.zeros(1), 0.0)
    first = f(np.ones(1), 1 / 30)
    assert 0.0 < first[0] < 1.0  # a step is smoothed, not passed through


def test_one_euro_reacts_faster_to_fast_motion():
    slow, fast = OneEuroFilter(1.0, 0.0), OneEuroFilter(1.0, 5.0)
    for f in (slow, fast):
        f(np.zeros(1), 0.0)
    assert fast(np.ones(1), 1 / 30)[0] > slow(np.ones(1), 1 / 30)[0]


# ----------------------------------------------------------------- mapping
def test_rotation_to_euler_identity():
    assert rotation_to_euler_deg(np.eye(4)) == pytest.approx((0.0, 0.0, 0.0), abs=1e-9)


def test_calibrator_handles_angle_wraparound():
    c = Calibrator(samples=2)
    c.feed(obs(pitch=179.0))
    c.feed(obs(pitch=-179.0))
    assert c.done
    assert abs(abs(c.neutral.pitch) - 180.0) < 1e-6


def test_mapping_basic_expressions():
    cfg = MappingConfig()
    neutral = Neutral()
    p = observation_to_params(obs(jawOpen=0.45, eyeBlinkRight=1.0, eyeBlinkLeft=0.0), neutral, cfg)
    assert p.mouth_open == pytest.approx(1.0)
    assert p.eye_open_l == pytest.approx(0.0)  # subject's right eye is the viewer's left
    assert p.eye_open_r == pytest.approx(1.0)
    smile = observation_to_params(obs(mouthSmileLeft=0.6, mouthSmileRight=0.6), neutral, cfg)
    assert smile.smile > 0.5
    frown = observation_to_params(obs(browDownLeft=0.8, browDownRight=0.8), neutral, cfg)
    assert frown.brow < -0.5


def test_mapping_uses_neutral_and_flags():
    neutral = Neutral(yaw=10.0, blink_l=0.2, blink_r=0.2)
    linear = MappingConfig(sensitivity=1.0)  # no response curve: angles map proportionally
    p = observation_to_params(obs(yaw=10.0 + 17.5, eyeBlinkRight=0.2), neutral, linear)
    assert p.yaw == pytest.approx(0.5)
    assert p.eye_open_l == pytest.approx(1.0)  # resting blink score counts as open
    inv = observation_to_params(obs(yaw=27.5), neutral, MappingConfig(invert_yaw=True, sensitivity=1.0))
    assert inv.yaw == pytest.approx(-0.5)
    swapped = observation_to_params(obs(eyeBlinkRight=1.0), Neutral(), MappingConfig(swap_eyes=True))
    assert swapped.eye_open_r == pytest.approx(0.0)


# ---------------------------------------------------------------- presence
def test_presence_transitions_and_fade():
    m = PresenceMachine(hold_s=1.0, fade_s=0.5)
    assert m.update(True, 0.0) is Presence.TRACKING
    for i in range(1, 20):
        m.update(True, i * 0.05)
    assert m.away_weight == 0.0
    assert m.update(False, 1.5) is Presence.HOLD
    assert m.update(False, 2.2) is Presence.AWAY
    for i in range(1, 20):
        m.update(False, 2.2 + i * 0.05)
    assert m.away_weight == 1.0


# -------------------------------------------------------------------- idle
def test_idle_is_deterministic_in_range_and_blinks():
    a, b = IdleAnimator(seed=3), IdleAnimator(seed=3)
    samples = [a.sample(i / 60) for i in range(600)]
    assert samples == [b.sample(i / 60) for i in range(600)]
    arr = np.stack([s.clipped().to_array() for s in samples])
    assert np.allclose(arr, np.stack([s.to_array() for s in samples]))
    assert min(s.eye_open_l for s in samples) < 0.2  # at least one blink in 10 s


# ------------------------------------------------------------------ avatar
def test_builtin_avatar_registered():
    assert "sprout" in available_avatars()
    with pytest.raises(ValueError):
        load_avatar("nope", 64, 36)


@pytest.mark.parametrize("w,h", [(640, 360), (1280, 720)])
def test_avatar_renders_extremes(w, h):
    av = load_avatar("sprout", w, h)
    for values in (AvatarParams(), AvatarParams(yaw=1, pitch=1, roll=0.8, mouth_open=1, smile=1, brow=1),
                   AvatarParams(yaw=-1, pitch=-1, roll=-0.8, eye_open_l=0, eye_open_r=0,
                                smile=-1, brow=-1, gaze_x=1, gaze_y=-1, breath=1)):
        frame = av.render(values, 1 / 30)
        assert frame.shape == (h, w, 3) and frame.dtype == np.uint8


def test_avatar_actually_changes_with_params():
    av = load_avatar("sprout", 320, 180, badge=False)
    closed = av.render(AvatarParams(), 1 / 30).copy()
    opened = av.render(AvatarParams(mouth_open=1.0), 1 / 30).copy()
    assert np.mean(np.abs(closed.astype(int) - opened.astype(int))) > 0.05


# ------------------------------------------------------------------ engine
class FakeMic:
    def mouth(self) -> float:
        return 0.8


def test_engine_calibrates_tracks_and_goes_away():
    eng = Engine(load_avatar("sprout", 320, 180), mic=FakeMic(), seed=0)
    t = 0.0
    for _ in range(20):  # calibrate on a neutral face
        t += 1 / 30
        eng.step(obs(t=t, yaw=5.0), t)
    assert eng.state.calibrated and eng.state.presence is Presence.TRACKING
    for _ in range(30):  # turn the head
        t += 1 / 30
        eng.step(obs(t=t, yaw=5.0 + 35.0, jawOpen=0.45), t)
    assert eng.state.params.yaw > 0.8 and eng.state.params.mouth_open > 0.8
    last = obs(t=t, yaw=5.0)
    for _ in range(90):  # face lost for 3 s: idle + mic drive the mouth
        t += 1 / 30
        eng.step(last, t)
    assert eng.state.presence is Presence.AWAY
    assert eng.state.params.mouth_open > 0.6
    assert math.isfinite(eng.state.params.yaw)


def test_sensitivity_boosts_small_movements_only():
    neutral = Neutral()
    small = obs(mouthSmileLeft=0.05, mouthSmileRight=0.05)
    base = observation_to_params(small, neutral, MappingConfig(sensitivity=1.0))
    boosted = observation_to_params(small, neutral, MappingConfig(sensitivity=1.5))
    assert boosted.smile > 1.5 * base.smile
    big = obs(jawOpen=0.45)
    assert observation_to_params(big, neutral, MappingConfig(sensitivity=1.5)).mouth_open == 1.0
