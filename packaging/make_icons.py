"""Render the app icons from the avatar itself: icon.png, icon.ico (Windows), icon.icns (macOS)."""

import sys
from pathlib import Path

from puppetcam.tray import avatar_icon

out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/icons")
out.mkdir(parents=True, exist_ok=True)
img = avatar_icon(None, size=1024)
img.save(out / "icon.png")
img.save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(out / "icon.icns")
print(f"wrote icons to {out}")
