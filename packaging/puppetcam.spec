# PyInstaller spec for the installed app: Puppetcam.app (macOS) and a folder for the
# Windows installer. Run from the repo root after `pip install .` and
# `python packaging/download_model.py` / `python packaging/make_icons.py`:
#
#     pyinstaller --noconfirm packaging/puppetcam.spec
#
# One folder, not one file: it starts faster and antivirus tools flag it less.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

import puppetcam
from puppetcam.tracker import BUNDLED_MODEL

if not BUNDLED_MODEL.exists():
    raise SystemExit("Face model missing: run python packaging/download_model.py first")

ROOT = Path(SPECPATH).parent  # noqa: F821 - defined by PyInstaller
ICONS = ROOT / "build" / "icons"
VERSION = puppetcam.__version__
# macOS: a "Developer ID Application: ..." identity signs every binary with the hardened
# runtime (needed for notarization). Unset = ad-hoc signature.
SIGN_IDENTITY = os.environ.get("MACOS_SIGN_IDENTITY") or None
ENTITLEMENTS = str(ROOT / "packaging" / "macos" / "entitlements.plist")

datas = collect_data_files("puppetcam")  # themes/*.toml and models/face_landmarker.task
binaries = []
hiddenimports = collect_submodules("puppetcam") + ["pystray._win32", "pystray._darwin"]
for pkg in ("mediapipe", "pyvirtualcam"):  # sounddevice: PyInstaller has a hook
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "puppetcam_app.py")],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "IPython", "pytest", "jax", "tensorflow", "torch"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="puppetcam",
    console=False,  # a tray app: no terminal window
    icon=str(ICONS / ("icon.ico" if sys.platform == "win32" else "icon.icns")),
    codesign_identity=SIGN_IDENTITY,
    entitlements_file=ENTITLEMENTS,
)
coll = COLLECT(exe, a.binaries, a.datas, name="puppetcam")  # noqa: F821

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="Puppetcam.app",
        icon=str(ICONS / "icon.icns"),
        bundle_identifier="io.github.cesaredavidepace.puppetcam",
        version=VERSION,
        info_plist={
            "CFBundleName": "Puppetcam",
            "CFBundleDisplayName": "Puppetcam",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSUIElement": True,  # menu bar app: no Dock icon
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSCameraUsageDescription":
                "Puppetcam tracks your face to animate the avatar. Frames never leave your Mac.",
            "NSMicrophoneUsageDescription":
                "When you step away, the avatar's mouth follows your voice. Audio is never stored.",
        },
    )
