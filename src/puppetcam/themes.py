"""Avatar themes: colors, proportions, accessories and background, in a TOML file.

A theme only needs the keys it changes; everything else comes from the
default. "I want it blue with glasses" is a three-line file::

    [colors]
    sweater = "#3b6fd4"

    [accessories]
    items = ["sprout", "glasses"]
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

BGR = tuple[int, int, int]

DEFAULT_COLORS: dict[str, str] = {
    "background_top": "#24344A",
    "background_bottom": "#3A5C78",
    "halo": "#547A96",
    "skin": "#F5CDAA",
    "ear_inner": "#ECA096",
    "sweater": "#D7963C",
    "eye": "#282837",
    "eye_shine": "#FAFAFA",
    "brow": "#6E463C",
    "mouth": "#5F283C",
    "tongue": "#EB6E82",
    "blush": "#FA9696",
    "stem": "#509646",
    "leaf_light": "#6EC85A",
    "leaf_dark": "#55A546",
    "glasses": "#2A2A33",
    "hat": "#C8463C",
    "headphones": "#34343E",
}
# Optional: derived automatically from the colors above when not given.
DERIVED_COLORS = ("skin_shade", "neck", "sweater_shade", "hat_band", "headphones_pad")

DEFAULT_SHAPE: dict[str, float] = {
    "head_roundness": 2.6,  # 2 = ellipse, higher = squarer
    "head_aspect": 0.93,  # height / width of the head
    "eye_size": 1.0,
    "eye_spacing": 1.0,
    "mouth_width": 1.0,
    "body_width": 1.0,
}
SHAPE_LIMITS: dict[str, tuple[float, float]] = {
    "head_roundness": (1.6, 6.0),
    "head_aspect": (0.75, 1.15),
    "eye_size": (0.6, 1.6),
    "eye_spacing": (0.75, 1.25),
    "mouth_width": (0.6, 1.6),
    "body_width": (0.7, 1.3),
}
ACCESSORIES = ("sprout", "glasses", "beanie", "headphones")


@dataclass(frozen=True)
class Theme:
    name: str
    avatar: str
    colors: dict[str, BGR]
    shape: dict[str, float]
    accessories: tuple[str, ...]
    background_image: Path | None = None


def parse_color(value: str | list[int], key: str = "color") -> BGR:
    """'#RRGGBB', '#RGB' or [r, g, b] -> OpenCV BGR tuple."""
    if isinstance(value, list | tuple) and len(value) == 3:
        r, g, b = (int(v) for v in value)
    elif isinstance(value, str) and value.startswith("#") and len(value) in (4, 7):
        h = value[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        try:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except ValueError:
            raise ValueError(f"{key}: invalid color {value!r}") from None
    else:
        raise ValueError(f"{key}: expected '#RRGGBB' or [r, g, b], got {value!r}")
    if not all(0 <= v <= 255 for v in (r, g, b)):
        raise ValueError(f"{key}: values must be 0-255, got {value!r}")
    return b, g, r


def _scale(c: BGR, k: float) -> BGR:
    return tuple(int(min(max(v * k, 0), 255)) for v in c)  # type: ignore[return-value]


def _mix(a: BGR, b: BGR, t: float) -> BGR:
    return tuple(int(x * (1 - t) + y * t) for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


def _check_keys(section: str, given: dict, allowed) -> None:
    unknown = set(given) - set(allowed)
    if unknown:
        raise ValueError(
            f"[{section}] unknown key(s): {', '.join(sorted(unknown))}. "
            f"Valid: {', '.join(sorted(allowed))}"
        )


def theme_from_dict(data: dict, base_dir: Path | None = None) -> Theme:
    _check_keys("theme", data, {"name", "avatar", "colors", "shape", "accessories", "background"})
    raw_colors = data.get("colors", {})
    _check_keys("colors", raw_colors, [*DEFAULT_COLORS, *DERIVED_COLORS])
    colors = {k: parse_color(raw_colors.get(k, v), k) for k, v in DEFAULT_COLORS.items()}
    derived = {
        "skin_shade": _scale(colors["skin"], 0.86),
        "neck": _scale(colors["skin"], 0.9),
        "sweater_shade": _scale(colors["sweater"], 0.8),
        "hat_band": _scale(colors["hat"], 0.78),
        "headphones_pad": _mix(colors["headphones"], (255, 255, 255), 0.18),
    }
    for k, v in derived.items():
        colors[k] = parse_color(raw_colors[k], k) if k in raw_colors else v

    raw_shape = data.get("shape", {})
    _check_keys("shape", raw_shape, DEFAULT_SHAPE)
    shape = {}
    for k, default in DEFAULT_SHAPE.items():
        lo, hi = SHAPE_LIMITS[k]
        shape[k] = min(max(float(raw_shape.get(k, default)), lo), hi)

    raw_acc = data.get("accessories", {})
    _check_keys("accessories", raw_acc, {"items"})
    items = tuple(raw_acc.get("items", ["sprout"]))
    bad = [i for i in items if i not in ACCESSORIES]
    if bad:
        raise ValueError(f"[accessories] unknown item(s) {bad}. Valid: {', '.join(ACCESSORIES)}")

    raw_bg = data.get("background", {})
    _check_keys("background", raw_bg, {"image"})
    image = None
    if raw_bg.get("image"):
        image = Path(raw_bg["image"]).expanduser()
        if not image.is_absolute() and base_dir is not None:
            image = base_dir / image

    return Theme(
        name=str(data.get("name", "custom")),
        avatar=str(data.get("avatar", "sprout")),
        colors=colors,
        shape=shape,
        accessories=items,
        background_image=image,
    )


def builtin_themes() -> list[str]:
    folder = files("puppetcam") / "themes"
    return sorted(p.name[:-5] for p in folder.iterdir() if p.name.endswith(".toml"))


def builtin_theme_text(name: str) -> str:
    return (files("puppetcam") / "themes" / f"{name}.toml").read_text(encoding="utf-8")


def load_theme(spec: str | Path | None = None) -> Theme:
    """Load a built-in theme by name, or a .toml file by path. None = default."""
    if spec is None:
        spec = "sprout"
    path = Path(spec).expanduser()
    if path.suffix == ".toml" or path.exists():
        if not path.exists():
            raise ValueError(f"Theme file not found: {path}")
        with path.open("rb") as fh:
            return theme_from_dict(tomllib.load(fh), path.parent)
    if str(spec) not in builtin_themes():
        raise ValueError(f"Unknown theme {spec!r}. Built-in: {', '.join(builtin_themes())}")
    return theme_from_dict(tomllib.loads(builtin_theme_text(str(spec))))
