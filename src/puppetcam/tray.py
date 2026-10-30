"""Menu bar (macOS) and tray (Windows, Linux) app: puppetcam without a terminal.

The icon's menu turns the avatar camera on and off and changes the theme,
sensitivity, camera and badge. Every change is saved to the settings file,
so ``puppetcam`` from a terminal starts the same way.

Threads: the icon owns the main thread (macOS requires it), the avatar runs
in a worker thread. On macOS, menu callbacks run on the main thread, which is
also where the camera permission prompt must happen, so sessions are built
right there.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
import webbrowser
from dataclasses import replace
from pathlib import Path

from . import __version__, autostart
from .settings import (
    SENSITIVITY_CHOICES,
    Settings,
    config_dir,
    load_settings,
    open_in_editor,
    save_settings,
    settings_path,
)
from .themes import builtin_themes, load_theme

log = logging.getLogger(__name__)

HELP_URL = "https://github.com/cesaredavidepace/puppetcam#something-doesnt-work"
CAMERAS = range(4)


def log_path() -> Path:
    return config_dir() / "puppetcam.log"


def avatar_icon(theme: str | None, size: int = 256, on: bool = True):
    """The avatar's own face as the app icon, in the current theme. Grey when off."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw

    from .avatars import load_avatar
    from .params import AvatarParams

    try:
        t = load_theme(theme)
    except ValueError:
        t = load_theme(None)
    n = max(512, round(size * 1.28))  # the head fills the middle 400/512 of a square frame
    frame = load_avatar(None, n, n, badge=False, theme=t).render(AvatarParams(smile=0.6), 0.0)
    top, left, side = round(n * 40 / 512), round(n * 56 / 512), round(n * 400 / 512)
    face = cv2.cvtColor(frame[top:top + side, left:left + side], cv2.COLOR_BGR2RGB)
    if not on:
        grey = cv2.cvtColor(face, cv2.COLOR_RGB2GRAY)
        face = np.stack([grey] * 3, axis=-1) // 2 + 64
    img = Image.fromarray(face).resize((size, size), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=255)
    img.putalpha(mask)
    return img


def _on_main_thread(fn) -> None:
    """Run fn where the UI toolkit expects it (AppKit only accepts the main thread)."""
    if sys.platform == "darwin":
        from PyObjCTools import AppHelper

        AppHelper.callAfter(fn)
    else:
        fn()


class SingleInstance:
    """A lock file so login autostart plus a manual launch don't fight over the webcam."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a+")
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._fh.close()
            raise RuntimeError("puppetcam is already running (look for its icon)") from None


class TrayApp:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.session = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.error: str | None = None
        self.icon = None

    # -- the avatar camera
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        from .app import RunConfig, Session

        if self.running:
            return
        self.error = None
        try:
            session = Session(RunConfig.from_settings(self.settings, preview=False))
        except Exception as exc:
            self._fail(exc)
            return
        self.session = session
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(session, self._stop),
                                        name="puppetcam-session", daemon=True)
        self._thread.start()
        self._refresh()

    def _run(self, session, stop: threading.Event) -> None:
        try:
            session.run(stop)
        except Exception as exc:
            self._fail(exc)
        finally:
            session.close()
            if self.session is session:
                self.session = None
            _on_main_thread(self._refresh)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._thread = None
        self.session = None
        self._refresh()

    def restart(self) -> None:
        if self.running:
            self.stop()
            self.start()

    def _fail(self, exc: BaseException) -> None:
        log.error("%s", exc, exc_info=not isinstance(exc, RuntimeError | ValueError))
        self.error = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        if self.icon is not None and self.icon.HAS_NOTIFICATION:
            try:
                self.icon.notify(self.error, "puppetcam")
            except Exception:
                log.debug("notification failed", exc_info=True)
        _on_main_thread(self._refresh)

    # -- settings
    def change(self, restart: bool = False, **changes) -> None:
        self.settings = replace(self.settings, **changes)
        try:
            save_settings(self.settings)
        except OSError as exc:
            log.error("Could not save settings: %s", exc)
        if restart:
            self.restart()

    def set_theme(self, theme: str) -> None:
        self.change(theme=theme)
        if self.session is not None:
            try:
                self.session.set_theme(theme)
            except Exception as exc:
                self._fail(exc)
        self._refresh()

    def set_sensitivity(self, value: float) -> None:
        self.change(sensitivity=value)
        if self.session is not None:
            self.session.set_sensitivity(value)

    def set_badge(self, badge: bool) -> None:
        self.change(badge=badge)
        if self.session is not None:
            self.session.set_badge(badge)

    def toggle_away(self) -> None:
        if self.session is not None:
            self.session.set_away(not self.session.engine.force_away)

    def toggle_autostart(self) -> None:
        try:
            autostart.set_enabled(not autostart.is_enabled())
        except OSError as exc:
            self._fail(exc)

    # -- the icon
    def status(self) -> str:
        if self.error:
            return f"⚠ {self.error}"
        return "Avatar camera is on" if self.running else "Avatar camera is off"

    def _refresh(self) -> None:
        if self.icon is None:
            return
        self.icon.icon = avatar_icon(self.settings.theme, on=self.running)
        self.icon.title = f"puppetcam: {self.status()}"
        self.icon.update_menu()

    def _theme_items(self):
        from pystray import MenuItem as Item

        def pick(name):
            return lambda icon, item: self.set_theme(name)

        def is_current(name):
            return lambda item: self.settings.theme == name

        names = builtin_themes()
        items = [Item(n.capitalize(), pick(n), checked=is_current(n), radio=True) for n in names]
        if self.settings.theme not in names:  # a .toml file of your own
            label = f"Custom: {Path(self.settings.theme).stem}"
            items.append(Item(label, pick(self.settings.theme), checked=lambda item: True, radio=True))
        return items

    def menu(self):
        from pystray import Menu
        from pystray import MenuItem as Item

        def status_clicked(icon, item):
            if self.error:
                webbrowser.open(HELP_URL)

        def sensitivity(value):
            return Item(f"{value:g}" + ("  (default)" if value == Settings.sensitivity else ""),
                        lambda icon, item: self.set_sensitivity(value),
                        checked=lambda item: self.settings.sensitivity == value, radio=True)

        def camera(index):
            return Item(f"Camera {index}", lambda icon, item: self.change(camera=index, restart=True),
                        checked=lambda item: self.settings.camera == index, radio=True)

        def quit_app(icon, item):
            self.stop()
            icon.stop()

        return Menu(
            Item(lambda item: self.status(), status_clicked, enabled=lambda item: bool(self.error)),
            Menu.SEPARATOR,
            Item("Avatar camera", lambda icon, item: self.stop() if self.running else self.start(),
                 checked=lambda item: self.running, default=True),
            Item("Recalibrate (relaxed face)", lambda icon, item: self.session and self.session.recalibrate(),
                 enabled=lambda item: self.running),
            Item("Away mode", lambda icon, item: self.toggle_away(),
                 checked=lambda item: bool(self.session and self.session.engine.force_away),
                 enabled=lambda item: self.running),
            Menu.SEPARATOR,
            Item("Theme", Menu(lambda: self._theme_items())),
            Item("Sensitivity", Menu(*(sensitivity(v) for v in SENSITIVITY_CHOICES))),
            Item("Camera", Menu(*(camera(i) for i in CAMERAS))),
            Item("Show AVATAR badge", lambda icon, item: self.set_badge(not self.settings.badge),
                 checked=lambda item: self.settings.badge),
            Menu.SEPARATOR,
            Item("Start at login", lambda icon, item: self.toggle_autostart(),
                 checked=lambda item: autostart.is_enabled()),
            Item("Open settings file", lambda icon, item: self._open_settings()),
            Item("Open log", lambda icon, item: open_in_editor(log_path())),
            Item(f"Quit puppetcam {__version__}", quit_app),
        )

    def _open_settings(self) -> None:
        path = settings_path()
        if not path.exists():
            save_settings(self.settings, path)
        open_in_editor(path)

    def run(self) -> None:
        import pystray

        self.start()  # on this (main) thread, before the icon takes it over
        self.icon = pystray.Icon("puppetcam", avatar_icon(self.settings.theme, on=self.running),
                                 f"puppetcam: {self.status()}", menu=self.menu())
        self.icon.run()


def _setup_logging() -> None:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    ]
    if sys.stderr is not None:  # None in a windowed app on Windows
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _hide_dock_icon() -> None:
    """macOS: a menu bar app has no Dock icon (the packaged app sets LSUIElement instead)."""
    if sys.platform != "darwin":
        return
    try:
        import AppKit

        AppKit.NSApplication.sharedApplication().setActivationPolicy_(
            AppKit.NSApplicationActivationPolicyAccessory)
    except Exception:
        log.debug("could not hide the Dock icon", exc_info=True)


def main() -> None:
    _setup_logging()
    try:
        import pystray  # noqa: F401
    except ImportError as exc:
        raise SystemExit(f"The tray app needs pystray: pip install 'puppetcam[tray]' ({exc})") from None
    try:
        lock = SingleInstance(config_dir() / "tray.lock")  # noqa: F841 - held until exit
        settings = load_settings()
    except (RuntimeError, ValueError) as exc:
        log.error("%s", exc)
        raise SystemExit(1) from None
    log.info("puppetcam %s tray, settings in %s", __version__, settings_path())
    _hide_dock_icon()
    TrayApp(settings).run()


if __name__ == "__main__":
    main()
