"""Saved settings: what you'd otherwise pass as flags every time.

A small TOML file in your user config folder. Command-line flags still win
over it, and ``puppetcam --theme winter --save`` writes them into it. The
tray app reads and writes the same file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    camera: int = 0
    theme: str = "sprout"
    avatar: str = ""  # empty = the avatar the theme was made for
    sensitivity: float = 1.5
    badge: bool = True
    size: str = "960x540"
    fps: int = 30
    track_fps: float = 30.0
    gpu: bool = False
    mic: bool = True
    invert_yaw: bool = False
    invert_pitch: bool = False
    invert_roll: bool = False
    swap_eyes: bool = False

    @property
    def width_height(self) -> tuple[int, int]:
        return parse_size(self.size)


COMMENTS = {
    "camera": "webcam index: 0 is the first camera, 1 the second...",
    "theme": "built-in theme name (puppetcam themes) or path to a .toml file",
    "avatar": 'avatar name (puppetcam avatars); "" = the one the theme was made for',
    "sensitivity": "above 1 exaggerates small movements, 1 = linear",
    "badge": "show the AVATAR label, so people know they're looking at an avatar",
    "size": "output resolution",
    "fps": "output frame rate",
    "track_fps": "tracking rate; 15 is about half the CPU and still smooth",
    "gpu": "try GPU tracking, falls back to CPU",
    "mic": "lip-sync from the microphone while you're away",
    "invert_yaw": "set if the avatar turns the wrong way",
    "invert_pitch": "set if the avatar nods the wrong way",
    "invert_roll": "set if the avatar tilts the wrong way",
    "swap_eyes": "set if the avatar winks with the wrong eye",
}

SENSITIVITY_CHOICES = (1.0, 1.2, 1.5, 2.0, 2.5)


def parse_size(s: str) -> tuple[int, int]:
    w, _, h = s.lower().partition("x")
    try:
        width, height = int(w), int(h)
    except ValueError:
        raise ValueError(f"size: expected WIDTHxHEIGHT like 960x540, got {s!r}") from None
    if width <= 0 or height <= 0:
        raise ValueError(f"size: expected WIDTHxHEIGHT like 960x540, got {s!r}")
    return width, height


def config_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "puppetcam"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "puppetcam"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "puppetcam"


def settings_path() -> Path:
    env = os.environ.get("PUPPETCAM_SETTINGS")
    return Path(env) if env else config_dir() / "settings.toml"


def _check_type(key: str, value, default) -> object:
    if isinstance(default, bool):
        ok = isinstance(value, bool)
    elif isinstance(default, float):
        ok = isinstance(value, int | float) and not isinstance(value, bool)
        value = float(value) if ok else value
    elif isinstance(default, int):
        ok = isinstance(value, int) and not isinstance(value, bool)
    else:
        ok = isinstance(value, str)
    if not ok:
        raise ValueError(f"{key}: expected {type(default).__name__}, got {value!r}")
    return value


def settings_from_dict(data: dict) -> Settings:
    defaults = Settings()
    known = {f.name for f in fields(Settings)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"unknown setting(s): {', '.join(sorted(unknown))}. "
                         f"Valid: {', '.join(sorted(known))}")
    values = {k: _check_type(k, v, getattr(defaults, k)) for k, v in data.items()}
    s = replace(defaults, **values)
    parse_size(s.size)
    if s.sensitivity <= 0:
        raise ValueError(f"sensitivity: must be above 0, got {s.sensitivity}")
    return s


def load_settings(path: Path | None = None) -> Settings:
    """The saved settings, or the defaults if there is no file yet."""
    path = path or settings_path()
    if not path.exists():
        return Settings()
    try:
        with path.open("rb") as fh:
            return settings_from_dict(tomllib.load(fh))
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        raise ValueError(f"{path}: {exc}") from None


def _toml_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        return repr(v)
    return json.dumps(v)  # a valid TOML basic string, backslashes escaped


def settings_to_toml(s: Settings) -> str:
    lines = ["# puppetcam settings. Command-line flags override these.", ""]
    for key, value in asdict(s).items():
        lines.append(f"# {COMMENTS[key]}")
        lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def save_settings(s: Settings, path: Path | None = None) -> Path:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(settings_to_toml(s), encoding="utf-8")
    os.replace(tmp, path)
    return path


def open_in_editor(path: Path) -> None:
    """Open a text file with the system's default editor."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-t", str(path)])
    elif sys.platform == "win32":
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError:  # no app associated with .toml / .log
            subprocess.Popen(["notepad", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
