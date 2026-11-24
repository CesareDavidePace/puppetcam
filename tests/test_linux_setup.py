"""Linux setup helpers: the root script, device detection, menu entry, Qt fonts (no root needed)."""

from __future__ import annotations

import os
import sys

import pytest

from puppetcam import linux_setup
from puppetcam.linux_setup import VcamStatus
from puppetcam.platform_tweaks import find_font_dir


def _status(**kw) -> VcamStatus:
    base = dict(installed=True, loaded=False, persistent=False, devices=[])
    return VcamStatus(**{**base, **kw})


def test_root_script_persists_and_loads(monkeypatch):
    script = linux_setup.root_script(_status())
    assert script.startswith("set -e\n")
    assert "/etc/modules-load.d/puppetcam.conf" in script
    assert "/etc/modprobe.d/puppetcam.conf" in script
    assert "exclusive_caps=1" in script and 'card_label="puppetcam"' in script
    assert script.rstrip().endswith("modprobe v4l2loopback")
    assert "apt-get" not in script  # already installed: nothing to install


def test_root_script_doesnt_reload_a_loaded_module():
    assert "modprobe v4l2loopback" not in linux_setup.root_script(_status(loaded=True))


def test_root_script_installs_with_apt_or_explains(monkeypatch):
    apt_only = {"apt-get": "/usr/bin/apt-get"}
    monkeypatch.setattr(linux_setup.shutil, "which", apt_only.get)
    assert "apt-get install -y v4l2loopback-dkms" in linux_setup.root_script(_status(installed=False))
    monkeypatch.setattr(linux_setup.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Fedora"):
        linux_setup.root_script(_status(installed=False))


@pytest.mark.skipif(sys.platform == "win32", reason="sysfs symlinks")
def test_loopback_devices_skips_real_webcams(tmp_path):
    devices = tmp_path / "devices"
    for path, name in [("pci0000:00/usb1/video0", "Integrated Webcam"),
                       ("virtual/video4linux/video10", "puppetcam"),
                       ("platform/v4l2loopback.0/video4linux/video2", "OBS Cam")]:
        d = devices / path
        d.mkdir(parents=True)
        (d / "name").write_text(name + "\n")
    cls = tmp_path / "class"
    cls.mkdir()
    for path in ["pci0000:00/usb1/video0", "virtual/video4linux/video10",
                 "platform/v4l2loopback.0/video4linux/video2"]:
        os.symlink(devices / path, cls / path.rsplit("/", 1)[1])
    assert linux_setup._loopback_devices(cls) == ["/dev/video2 (OBS Cam)", "/dev/video10 (puppetcam)"]


def test_desktop_entry():
    text = linux_setup.desktop_entry(["/opt/py/bin/python", "-m", "puppetcam", "run", "--notify-errors"],
                                     ["/opt/py/bin/python", "-m", "puppetcam", "tray"],
                                     linux_setup.icon_path())
    assert "Exec=/opt/py/bin/python -m puppetcam run --notify-errors\n" in text
    assert "[Desktop Action tray]" in text and "Terminal=false" in text


def test_find_font_dir(tmp_path):
    empty, fonts, nested = tmp_path / "empty", tmp_path / "dejavu", tmp_path / "root" / "x" / "noto"
    for d in (empty, fonts, nested):
        d.mkdir(parents=True)
    (fonts / "DejaVuSans.ttf").write_bytes(b"")
    (nested / "Noto.otf").write_bytes(b"")
    assert find_font_dir([str(empty), str(fonts)], root=str(tmp_path / "none")) == str(fonts)
    assert find_font_dir([str(empty)], root=str(tmp_path / "root")) == str(nested)
    assert find_font_dir([str(empty)], root=str(tmp_path / "none")) is None


def test_setup_dry_run_prints_the_root_script(monkeypatch, capsys):
    from puppetcam.cli import main

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(linux_setup, "status", lambda: _status())
    main(["setup", "--dry-run"])
    assert "modprobe v4l2loopback" in capsys.readouterr().out


def test_fix_qt_fonts_replaces_a_folder_without_fonts(tmp_path, monkeypatch):
    from puppetcam import platform_tweaks

    good = tmp_path / "good"
    good.mkdir()
    (good / "DejaVuSans.ttf").write_bytes(b"")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(platform_tweaks, "find_font_dir", lambda: str(good))
    monkeypatch.setenv("QT_QPA_FONTDIR", str(tmp_path / "cv2" / "qt" / "fonts"))  # missing, as in #1
    assert platform_tweaks.fix_qt_fonts() == str(good)
    assert os.environ["QT_QPA_FONTDIR"] == str(good)
    other = tmp_path / "opencv-fonts"
    other.mkdir()
    (other / "a.ttf").write_bytes(b"")
    monkeypatch.setenv("QT_QPA_FONTDIR", str(other))  # opencv ships fonts: keep them
    assert platform_tweaks.fix_qt_fonts() == str(other)
