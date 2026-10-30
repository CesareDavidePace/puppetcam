"""Command line entry point: ``puppetcam [run|tray|settings|bench|demo|themes|doctor|...]``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .settings import Settings, parse_size

BOOL = argparse.BooleanOptionalAction


def _size_str(s: str) -> str:
    w, h = parse_size(s)
    return f"{w}x{h}"


# Flags with the same name as a saved setting default to None: "not given, use the setting".
def _add_run_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("input")
    g.add_argument("--camera", type=int, help="webcam index (default 0)")
    g.add_argument("--cam-size", type=parse_size, default=(640, 480), help="capture size, e.g. 640x480")
    g.add_argument("--track-fps", type=float, help="max tracking rate; 15 halves CPU (default 30)")
    g.add_argument("--away-track-fps", type=float, default=4.0,
                   help="tracking rate while you're away (just to notice you're back)")
    g.add_argument("--gpu", action=BOOL, help="try GPU tracking (falls back to CPU)")
    g.add_argument("--track-width", type=int, default=None,
                   help="downscale frames to this width before tracking (e.g. 480)")
    g.add_argument("--model", type=Path, default=None, help="path to face_landmarker.task")
    g.add_argument("--mic", action=BOOL, help="lip-sync from the microphone when away (default on)")

    g = p.add_argument_group("output")
    g.add_argument("--size", type=_size_str, help="output size, e.g. 1280x720 (default 960x540)")
    g.add_argument("--fps", type=int, help="output frame rate (default 30)")
    g.add_argument("--theme", help="theme name or .toml file (see: puppetcam themes)")
    g.add_argument("--avatar", help="avatar name (see: puppetcam avatars)")
    g.add_argument("--badge", action=BOOL, help="show the 'AVATAR' label (default on)")
    g.add_argument("--no-vcam", action="store_true", help="preview only, no virtual camera")
    g.add_argument("--no-preview", action="store_true", help="run headless")
    g.add_argument("--vcam-device", default=None)
    g.add_argument("--vcam-backend", default=None, help="obs | unitycapture | v4l2loopback")

    g = p.add_argument_group("mapping (if the avatar moves the wrong way)")
    g.add_argument("--invert-yaw", action=BOOL)
    g.add_argument("--invert-pitch", action=BOOL)
    g.add_argument("--invert-roll", action=BOOL)
    g.add_argument("--swap-eyes", action=BOOL)
    g.add_argument("--sensitivity", type=float,
                   help="above 1 exaggerates small movements, 1 = linear (default 1.5)")
    p.add_argument("--stats", action="store_true", help="log fps and timings every 5 s")
    p.add_argument("--save", action="store_true",
                   help="save the options above as your defaults (see: puppetcam settings)")


def settings_with_args(base: Settings, a: argparse.Namespace) -> Settings:
    """The saved settings, overridden by the flags given on the command line."""
    from .settings import settings_from_dict

    given = {k: v for k, v in vars(a).items() if k in Settings.__dataclass_fields__ and v is not None}
    theme = Path(given.get("theme", "")).expanduser()
    if theme.suffix == ".toml":  # a file: keep working from any folder once saved
        given["theme"] = str(theme.resolve())
    data = {**vars(base), **given}
    return settings_from_dict(data)


def _cmd_run(a: argparse.Namespace) -> None:
    from .app import RunConfig, run
    from .settings import load_settings, save_settings

    s = settings_with_args(load_settings(), a)
    if a.save:
        print(f"saved to {save_settings(s)}")
    run(RunConfig.from_settings(
        s, cam_width=a.cam_size[0], cam_height=a.cam_size[1],
        away_track_fps=a.away_track_fps, track_width=a.track_width,
        vcam=not a.no_vcam, vcam_device=a.vcam_device, vcam_backend=a.vcam_backend,
        preview=not a.no_preview, model=a.model, stats=a.stats,
    ))


def _cmd_tray(a: argparse.Namespace) -> None:
    from .tray import main as tray_main

    tray_main()


def _cmd_settings(a: argparse.Namespace) -> None:
    from .settings import load_settings, open_in_editor, save_settings, settings_path, settings_to_toml

    path = settings_path()
    if a.reset:
        path.unlink(missing_ok=True)
        print(f"removed {path}: back to the defaults")
        return
    if a.edit:
        if not path.exists():
            save_settings(load_settings(), path)
        open_in_editor(path)
        print(f"opened {path}")
        return
    print(f"# {path}" + ("" if path.exists() else "  (not created yet: these are the defaults)"))
    print(settings_to_toml(load_settings()), end="")


def _cmd_bench(a: argparse.Namespace) -> None:
    from .tools import bench_render, bench_tracker

    for line in bench_render(a.sizes, avatar=a.avatar, theme=a.theme):
        print(line)
    if a.video is not None:
        widths = [None if w == 0 else w for w in a.track_widths]
        for line in bench_tracker(a.video, widths, gpu=a.gpu):
            print(line)
    else:
        print("track   (skipped: pass --video FILE or --video 0 for the webcam)")


def _cmd_demo(a: argparse.Namespace) -> None:
    from .tools import render_demo

    render_demo(a.out, *a.size, avatar=a.avatar, theme=a.theme)
    print(f"wrote {a.out}")


def _cmd_download(a: argparse.Namespace) -> None:
    from .tracker import ensure_model

    print(ensure_model(a.model))


def _cmd_themes(a: argparse.Namespace) -> None:
    from .themes import builtin_theme_text, builtin_themes, load_theme

    if a.export:
        name, out = a.export
        if name not in builtin_themes():
            raise RuntimeError(f"Unknown theme {name!r}. Built-in: {', '.join(builtin_themes())}")
        Path(out).write_text(builtin_theme_text(name), encoding="utf-8")
        print(f"wrote {out}  (edit it, then: puppetcam --theme {out})")
        return
    if a.check:
        theme = load_theme(a.check)
        print(f"ok: {theme.name}  accessories={list(theme.accessories)}")
        return
    for name in builtin_themes():
        t = load_theme(name)
        print(f"{name:10} {', '.join(t.accessories) or '-'}")


def _cmd_avatars(a: argparse.Namespace) -> None:
    from .avatars.base import available_avatars

    for name, target in sorted(available_avatars().items()):
        print(f"{name:12} {target}")


def _cmd_doctor(a: argparse.Namespace) -> None:
    from .doctor import run_checks
    from .settings import load_settings

    camera = a.camera if a.camera is not None else load_settings().camera
    if not run_checks(camera=camera, vcam=not a.no_vcam):
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="puppetcam", description="Animated avatar webcam, 100%% local.")
    p.add_argument("--version", action="version", version=f"puppetcam {__version__}")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="start the avatar camera (default)")
    _add_run_args(r)
    r.set_defaults(func=_cmd_run)

    t = sub.add_parser("tray", help="menu bar / tray app: on/off, theme, sensitivity, start at login")
    t.set_defaults(func=_cmd_tray)

    st = sub.add_parser("settings", help="show the saved settings (change them with: puppetcam ... --save)")
    st.add_argument("--edit", action="store_true", help="open the settings file in a text editor")
    st.add_argument("--reset", action="store_true", help="delete the file, back to the defaults")
    st.set_defaults(func=_cmd_settings)

    b = sub.add_parser("bench", help="measure render and tracking cost")
    b.add_argument("--sizes", type=parse_size, nargs="+", default=[(640, 360), (960, 540), (1280, 720)])
    b.add_argument("--video", default=None, help="video file or camera index for tracker timing")
    b.add_argument("--track-widths", type=int, nargs="+", default=[320, 480, 0],
                   help="0 = native width")
    b.add_argument("--avatar", default=None)
    b.add_argument("--theme", default=None)
    b.add_argument("--gpu", action="store_true")
    b.set_defaults(func=_cmd_bench)

    d = sub.add_parser("demo", help="render a scripted clip (mp4 or gif), no webcam")
    d.add_argument("out", type=Path, nargs="?", default=Path("demo.mp4"))
    d.add_argument("--size", type=parse_size, default=(640, 360))
    d.add_argument("--avatar", default=None)
    d.add_argument("--theme", default=None)
    d.set_defaults(func=_cmd_demo)

    th = sub.add_parser("themes", help="list built-in themes, export one to customize, or check a file")
    th.add_argument("--export", nargs=2, metavar=("NAME", "FILE"), help="copy a built-in theme to FILE")
    th.add_argument("--check", metavar="FILE", help="validate a theme file")
    th.set_defaults(func=_cmd_themes)

    m = sub.add_parser("download-model", help="fetch the MediaPipe face model once")
    m.add_argument("--model", type=Path, default=None)
    m.set_defaults(func=_cmd_download)

    av = sub.add_parser("avatars", help="list installed avatars")
    av.set_defaults(func=_cmd_avatars)

    dr = sub.add_parser("doctor", help="check camera, model, microphone and virtual camera")
    dr.add_argument("--camera", type=int, help="webcam index (default: the saved one)")
    dr.add_argument("--no-vcam", action="store_true", help="skip the virtual camera check")
    dr.set_defaults(func=_cmd_doctor)
    return p


COMMANDS = {"run", "tray", "settings", "bench", "demo", "themes", "download-model", "avatars", "doctor"}
VERBOSE = ("-v", "--verbose")


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `puppetcam` and `puppetcam --size 1280x720` both mean `puppetcam run ...`
    first = next((a for a in argv if a not in VERBOSE), None)
    if first is None or (first not in COMMANDS and first not in ("-h", "--help", "--version")):
        i = 0
        while i < len(argv) and argv[i] in VERBOSE:
            i += 1
        argv.insert(i, "run")
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        args.func(args)
    except (RuntimeError, ValueError) as exc:
        logging.getLogger("puppetcam").error("%s", exc)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
