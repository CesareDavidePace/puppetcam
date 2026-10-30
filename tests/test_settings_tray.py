"""Saved settings, start at login and the tray app's logic (no webcam, no icon shown)."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from puppetcam import autostart
from puppetcam.cli import build_parser, settings_with_args
from puppetcam.settings import (
    Settings,
    load_settings,
    save_settings,
    settings_from_dict,
    settings_to_toml,
)


@pytest.fixture
def settings_file(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "settings.toml"
    monkeypatch.setenv("PUPPETCAM_SETTINGS", str(path))
    return path


# ------------------------------------------------------------------ settings
def test_settings_default_when_missing_and_roundtrip(settings_file):
    assert load_settings() == Settings()
    s = Settings(theme="winter", sensitivity=2.0, badge=False, size="1280x720", camera=1)
    save_settings(s)
    assert load_settings() == s
    assert "# show the AVATAR label" in settings_file.read_text(encoding="utf-8")


def test_settings_windows_path_roundtrip(settings_file):
    s = Settings(theme=r"C:\Users\me\my theme.toml")
    save_settings(s)
    assert load_settings().theme == s.theme


def test_settings_validation(settings_file):
    assert settings_from_dict({"sensitivity": 2}).sensitivity == 2.0  # int is fine for a float
    with pytest.raises(ValueError, match="thme"):
        settings_from_dict({"thme": "winter"})
    with pytest.raises(ValueError, match="badge"):
        settings_from_dict({"badge": "yes"})
    with pytest.raises(ValueError, match="size"):
        settings_from_dict({"size": "big"})
    settings_file.write_text("camera = ", encoding="utf-8")
    with pytest.raises(ValueError, match="settings.toml"):
        load_settings()


def test_toml_output_parses_back():
    import tomllib

    assert settings_from_dict(tomllib.loads(settings_to_toml(Settings()))) == Settings()


def test_flags_override_saved_settings(tmp_path):
    base = Settings(theme="winter", badge=False, sensitivity=2.0)
    a = build_parser().parse_args(["run", "--badge", "--size", "1280x720"])
    s = settings_with_args(base, a)
    assert (s.theme, s.badge, s.size, s.sensitivity) == ("winter", True, "1280x720", 2.0)
    assert settings_with_args(base, build_parser().parse_args(["run"])) == base
    a = build_parser().parse_args(["run", "--theme", str(tmp_path / ".." / "t.toml")])
    assert Path(settings_with_args(base, a).theme).is_absolute()
    assert ".." not in settings_with_args(base, a).theme


def test_old_flags_still_work():
    a = build_parser().parse_args(["run", "--no-badge", "--no-mic", "--gpu", "--invert-yaw"])
    s = settings_with_args(Settings(), a)
    assert (s.badge, s.mic, s.gpu, s.invert_yaw) == (False, False, True, True)


# ------------------------------------------------------------------ start at login
def test_launch_command_runs_the_tray():
    assert autostart.launch_command()[-3:] == ["-m", "puppetcam", "tray"]


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_autostart_files(platform, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    assert not autostart.is_enabled()
    autostart.enable()
    assert autostart.is_enabled()
    if platform == "darwin":
        import plistlib

        agent = tmp_path / "Library" / "LaunchAgents" / f"{autostart.LABEL}.plist"
        plist = plistlib.loads(agent.read_bytes())
        assert plist["RunAtLoad"] and plist["ProgramArguments"][-1] == "tray"
    else:
        text = (tmp_path / ".config" / "autostart" / "puppetcam.desktop").read_text(encoding="utf-8")
        assert "Exec=" in text and text.rstrip().endswith("true")
    autostart.disable()
    assert not autostart.is_enabled()
    autostart.disable()  # twice is fine


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry")
def test_autostart_registry(monkeypatch):
    monkeypatch.setattr(autostart, "RUN_VALUE", "puppetcam-test")
    autostart.enable()
    try:
        assert autostart.is_enabled()
    finally:
        autostart.disable()
    assert not autostart.is_enabled()


# ------------------------------------------------------------------ tray
class FakeSession:
    fail_on_init: Exception | None = None

    def __init__(self, cfg) -> None:
        if FakeSession.fail_on_init:
            raise FakeSession.fail_on_init
        self.cfg = cfg
        self.theme = cfg.theme
        self.sensitivity = cfg.mapping.sensitivity
        self.closed = False
        self.running = threading.Event()

    def run(self, stop) -> None:
        self.running.set()
        stop.wait()

    def set_theme(self, spec):
        self.theme = spec

    def set_sensitivity(self, s):
        self.sensitivity = s

    def close(self):
        self.closed = True


@pytest.fixture
def tray(settings_file, monkeypatch):
    import puppetcam.app
    from puppetcam.tray import TrayApp

    monkeypatch.setattr(puppetcam.app, "Session", FakeSession)
    FakeSession.fail_on_init = None
    app = TrayApp()
    yield app
    app.stop()


def test_tray_start_stop_and_live_changes(tray, settings_file):
    tray.start()
    assert tray.running and not tray.session.cfg.preview
    session = tray.session
    session.running.wait(2)
    tray.set_theme("winter")
    tray.set_sensitivity(2.0)
    assert (session.theme, session.sensitivity) == ("winter", 2.0)
    assert load_settings().theme == "winter" and load_settings().sensitivity == 2.0
    tray.change(camera=1, restart=True)  # a new camera needs a new session
    assert tray.running and tray.session is not session and session.closed
    assert tray.session.cfg.camera == 1
    tray.stop()
    assert not tray.running and tray.status() == "Avatar camera is off"


def test_tray_reports_startup_errors(tray):
    FakeSession.fail_on_init = RuntimeError("No virtual camera backend found. Install one:\n  ...")
    tray.start()
    assert not tray.running
    assert tray.status() == "⚠ No virtual camera backend found. Install one:"


def test_tray_icon_and_single_instance(tmp_path):
    from puppetcam.tray import SingleInstance, avatar_icon

    img = avatar_icon("winter", size=64)
    assert img.size == (64, 64) and img.mode == "RGBA"
    assert img.getpixel((0, 0))[3] == 0  # rounded corner
    assert avatar_icon("no-such-theme", size=32, on=False).size == (32, 32)

    lock = SingleInstance(tmp_path / "tray.lock")  # noqa: F841
    with pytest.raises(RuntimeError, match="already running"):
        SingleInstance(tmp_path / "tray.lock")


def test_tray_menu_builds(tray):
    pytest.importorskip("pystray", exc_type=Exception)  # Linux CI has no desktop
    menu = tray.menu()
    texts = [item.text for item in menu.items]
    assert "Avatar camera is off" in texts and "Start at login" in texts
    theme_menu = next(i for i in menu.items if i.text == "Theme").submenu
    assert any(i.checked for i in theme_menu.items)
