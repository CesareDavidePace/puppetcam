"""Start the tray app when you log in.

Uses the plain per-user mechanism of each OS, no admin rights needed:

- macOS: a LaunchAgent in ~/Library/LaunchAgents
- Windows: the HKCU ...\\CurrentVersion\\Run registry key (the installer uses the same value)
- Linux: an XDG autostart .desktop file
"""

from __future__ import annotations

import os
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

LABEL = "io.github.cesaredavidepace.puppetcam"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "puppetcam"


def launch_command() -> list[str]:
    """How to start the tray app from scratch: the installed app, or this Python."""
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):
        app = next((p for p in exe.parents if p.suffix == ".app"), None)
        return ["/usr/bin/open", str(app)] if app else [str(exe)]
    if sys.platform == "win32" and (exe.parent / "pythonw.exe").exists():
        exe = exe.parent / "pythonw.exe"  # no console window
    return [str(exe), "-m", "puppetcam", "tray"]


def _launch_agent() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _desktop_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / "puppetcam.desktop"


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, RUN_VALUE)
            return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return _launch_agent().exists()
    return _desktop_file().exists()


def enable() -> None:
    cmd = launch_command()
    if sys.platform == "win32":
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
    elif sys.platform == "darwin":
        path = _launch_agent()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plistlib.dumps({
            "Label": LABEL,
            "ProgramArguments": cmd,
            "RunAtLoad": True,
            "ProcessType": "Interactive",
        }))
    else:
        path = _desktop_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=puppetcam\n"
            "Comment=Animated avatar webcam\n"
            f"Exec={shlex.join(cmd)}\n"
            "X-GNOME-Autostart-enabled=true\n",
            encoding="utf-8",
        )


def disable() -> None:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, RUN_VALUE)
        except FileNotFoundError:
            pass
    elif sys.platform == "darwin":
        _launch_agent().unlink(missing_ok=True)
    else:
        _desktop_file().unlink(missing_ok=True)


def set_enabled(enabled: bool) -> None:
    enable() if enabled else disable()
