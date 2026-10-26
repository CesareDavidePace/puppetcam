"""Themes, accessories and the platform/away-mode plumbing."""

from __future__ import annotations

import sys

import cv2
import numpy as np
import pytest

from puppetcam.avatars import load_avatar
from puppetcam.params import AvatarParams
from puppetcam.platform_tweaks import disable_app_nap, set_current_thread_efficiency
from puppetcam.themes import builtin_themes, load_theme, parse_color, theme_from_dict


def test_parse_color_formats():
    assert parse_color("#FF8000") == (0, 128, 255)  # BGR
    assert parse_color("#f80") == (0, 136, 255)
    assert parse_color([255, 128, 0]) == (0, 128, 255)
    for bad in ("red", "#12345", [300, 0, 0]):
        with pytest.raises(ValueError):
            parse_color(bad)


def test_partial_theme_falls_back_to_defaults_and_derives_shades():
    default = load_theme(None)
    t = theme_from_dict({"colors": {"sweater": "#3B6FD4"}, "accessories": {"items": ["glasses"]}})
    assert t.colors["sweater"] == (0xD4, 0x6F, 0x3B)
    assert t.colors["skin"] == default.colors["skin"]
    assert t.colors["sweater_shade"] != default.colors["sweater_shade"]  # derived from the new sweater
    assert t.accessories == ("glasses",)


def test_theme_validation_messages():
    with pytest.raises(ValueError, match="sweatr"):
        theme_from_dict({"colors": {"sweatr": "#000000"}})
    with pytest.raises(ValueError, match="crown"):
        theme_from_dict({"accessories": {"items": ["crown"]}})
    t = theme_from_dict({"shape": {"eye_size": 99}})
    assert t.shape["eye_size"] == 1.6  # clamped


def test_theme_file_with_background_image(tmp_path):
    img = np.zeros((100, 300, 3), np.uint8)
    img[:, :, 2] = 200  # red
    cv2.imwrite(str(tmp_path / "bg.png"), img)
    (tmp_path / "t.toml").write_text('[background]\nimage = "bg.png"\n', encoding="utf-8")
    theme = load_theme(tmp_path / "t.toml")
    assert theme.background_image == tmp_path / "bg.png"
    frame = load_avatar(None, 320, 180, badge=False, theme=theme).render(AvatarParams(), 1 / 30)
    assert frame[2, 2, 2] > 150  # corner shows the picture, cropped to fill


def test_missing_theme_errors():
    with pytest.raises(ValueError):
        load_theme("does-not-exist")
    with pytest.raises(ValueError):
        load_theme("missing.toml")


@pytest.mark.parametrize("name", builtin_themes())
def test_every_builtin_theme_renders(name):
    av = load_avatar(None, 480, 270, theme=load_theme(name))
    for p in (AvatarParams(), AvatarParams(yaw=0.9, roll=0.5, mouth_open=1, eye_open_r=0),
              AvatarParams(yaw=-0.9, pitch=1, smile=1, brow=1)):
        frame = av.render(p, 1 / 30)
        assert frame.shape == (270, 480, 3)


def test_accessories_change_the_picture():
    params = AvatarParams()
    plain = load_avatar(None, 320, 180, badge=False, theme=theme_from_dict({"accessories": {"items": []}}))
    base = plain.render(params, 1 / 30).copy()
    for item in ("sprout", "glasses", "beanie", "headphones"):
        av = load_avatar(None, 320, 180, badge=False,
                         theme=theme_from_dict({"accessories": {"items": [item]}}))
        assert np.mean(np.abs(av.render(params, 1 / 30).astype(int) - base.astype(int))) > 0.1, item


def test_platform_tweaks_are_safe_everywhere():
    assert disable_app_nap() in (True, False)
    assert set_current_thread_efficiency(True) in (True, False)
    assert set_current_thread_efficiency(False) in (True, False)
    if sys.platform.startswith("linux"):
        assert set_current_thread_efficiency(True) is False


class FakeCap:
    def __init__(self):
        self.reads = 0

    def set(self, *a):
        return True

    def get(self, *a):
        return 0.0

    def grab(self):
        return True

    def read(self):
        self.reads += 1
        return True, np.zeros((48, 64, 3), np.uint8)

    def release(self):
        pass


class CountingTracker:
    def __init__(self):
        self.calls = 0

    def process(self, frame, t):
        self.calls += 1
        return None


def test_sensor_tracks_slowly_when_away(monkeypatch):
    import time

    import puppetcam.capture as capture

    monkeypatch.setattr(capture, "open_camera", lambda *a, **k: FakeCap())

    def calls_in(away: bool, seconds: float = 0.6) -> int:
        tracker = CountingTracker()
        s = capture.SensorThread(tracker, track_fps=30, away_track_fps=4)
        s.set_away(away)
        s.start()
        time.sleep(seconds)
        s.stop()
        s.join(1.0)
        return tracker.calls

    active, away = calls_in(False), calls_in(True)
    assert active > 10
    assert away <= 4


def test_windows_app_control_block_gets_a_readable_error(monkeypatch, tmp_path):
    from mediapipe.tasks.python import vision

    from puppetcam.tracker import FaceTracker

    def blocked(options):
        exc = OSError("An Application Control policy has blocked this file")
        exc.winerror = 4551
        raise exc

    monkeypatch.setattr(vision.FaceLandmarker, "create_from_options", blocked)
    model = tmp_path / "face_landmarker.task"
    model.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="Smart App Control"):
        FaceTracker(model)
