"""Avatar interface and plugin registry.

An avatar is anything that turns ``AvatarParams`` into a BGR frame.
Third-party packages can add avatars without touching this repo by
declaring an entry point::

    [project.entry-points."puppetcam.avatars"]
    robot = "my_package.robot:RobotAvatar"
"""

from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from importlib.metadata import entry_points

import numpy as np

from ..params import AvatarParams
from ..themes import Theme, load_theme

ENTRY_POINT_GROUP = "puppetcam.avatars"
BUILTIN = {"sprout": "puppetcam.avatars.sprout:SproutAvatar"}


class Avatar(ABC):
    name = "base"

    def __init__(self, width: int, height: int, badge: bool = True, theme: Theme | None = None) -> None:
        self.width = width
        self.height = height
        self.badge = badge
        self.theme = theme or load_theme(None)

    @abstractmethod
    def render(self, params: AvatarParams, dt: float) -> np.ndarray:
        """Return an HxWx3 uint8 BGR frame.

        ``dt`` is the time since the previous frame, for avatars with their own
        secondary motion. Implementations may return the same buffer every
        call: the caller must not keep references across frames.
        """


def available_avatars() -> dict[str, str]:
    found = dict(BUILTIN)
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        found.setdefault(ep.name, ep.value)
    return found


def load_avatar(
    name: str | None, width: int, height: int, badge: bool = True, theme: Theme | None = None
) -> Avatar:
    """``name=None`` uses the avatar the theme was made for."""
    name = name or (theme.avatar if theme else "sprout")
    targets = available_avatars()
    if name not in targets:
        raise ValueError(f"Unknown avatar {name!r}. Available: {', '.join(sorted(targets))}")
    module_name, _, attr = targets[name].partition(":")
    cls = getattr(importlib.import_module(module_name), attr)
    return cls(width, height, badge=badge, theme=theme)
