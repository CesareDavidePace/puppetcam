"""``puppetcam setup`` on Linux: the virtual camera in one step, kept after a reboot.

What it does, asking for the password once (sudo in a terminal, the desktop's
password dialog otherwise):

1. installs ``v4l2loopback`` if the kernel module is missing (apt-based distros;
   other distros get the exact command to run),
2. writes ``/etc/modules-load.d/puppetcam.conf`` and ``/etc/modprobe.d/puppetcam.conf``
   so the camera comes back by itself after a reboot,
3. loads the module now.

Then, without root, it adds Puppetcam to the applications menu.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

LABEL = "puppetcam"
MODULE = "v4l2loopback"
OPTIONS = f'devices=1 exclusive_caps=1 card_label="{LABEL}"'
MODULES_LOAD = Path("/etc/modules-load.d/puppetcam.conf")
MODPROBE_CONF = Path("/etc/modprobe.d/puppetcam.conf")
SYS_MODULE = Path("/sys/module") / MODULE
SYS_VIDEO = Path("/sys/class/video4linux")

OTHER_DISTROS = """\
Install the v4l2loopback kernel module with your package manager, then run puppetcam setup again:
  Fedora:        enable RPM Fusion, then: sudo dnf install akmod-v4l2loopback
  Arch, Manjaro: sudo pacman -S v4l2loopback-dkms linux-headers
  openSUSE:      sudo zypper install v4l2loopback-kmp-default"""

SECURE_BOOT = """\
The kernel refused the module, most likely because Secure Boot is on and the module
built by DKMS isn't signed. Reboot: a blue "MOK management" screen asks for the
password you chose while installing; pick "Enroll MOK". Then run puppetcam setup again."""


@dataclass
class VcamStatus:
    installed: bool  # the kernel module exists for the running kernel
    loaded: bool  # the module is loaded right now
    persistent: bool  # it's loaded again after a reboot
    devices: list[str]  # names of the loopback cameras, e.g. ["/dev/video10 (puppetcam)"]

    @property
    def ready(self) -> bool:
        return self.loaded and bool(self.devices)


def _loopback_devices(root: Path = SYS_VIDEO) -> list[str]:
    """Loopback cameras have no hardware behind them: they live under /sys/devices/virtual
    (or /sys/devices/platform/v4l2loopback.N in newer versions), webcams under usb/pci."""
    found = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (len(p.name), p.name))
    except OSError:
        return found
    for entry in entries:
        real = os.path.realpath(entry)
        if "/virtual/" not in real and "v4l2loopback" not in real:
            continue
        try:
            name = (entry / "name").read_text(errors="replace").strip()
        except OSError:
            name = ""
        found.append(f"/dev/{entry.name} ({name})" if name else f"/dev/{entry.name}")
    return found


def _module_installed() -> bool:
    if SYS_MODULE.exists():
        return True
    modinfo = shutil.which("modinfo") or "/sbin/modinfo"
    try:
        return subprocess.run([modinfo, MODULE], capture_output=True).returncode == 0
    except OSError:
        return False


def _persistent() -> bool:
    if MODULES_LOAD.exists():
        return True
    for folder in ("/etc/modules-load.d", "/usr/lib/modules-load.d", "/lib/modules-load.d"):
        try:
            for f in Path(folder).glob("*.conf"):
                if any(line.strip() == MODULE for line in f.read_text(errors="replace").splitlines()):
                    return True
        except OSError:
            continue
    try:  # Debian's classic list
        return any(line.split()[:1] == [MODULE] for line in Path("/etc/modules").read_text().splitlines())
    except OSError:
        return False


def status() -> VcamStatus:
    loaded = SYS_MODULE.exists()
    return VcamStatus(installed=_module_installed(), loaded=loaded,
                      persistent=_persistent(), devices=_loopback_devices() if loaded else [])


def install_command() -> str | None:
    """The command that installs the module on this distro, if we can run it safely."""
    if shutil.which("apt-get"):
        return "DEBIAN_FRONTEND=noninteractive apt-get install -y v4l2loopback-dkms"
    return None


def root_script(st: VcamStatus) -> str:
    """Everything that needs root, as one shell script (one password prompt)."""
    lines = ["set -e"]
    if not st.installed:
        cmd = install_command()
        if cmd is None:
            raise RuntimeError(OTHER_DISTROS)
        lines.append(cmd)
    lines += [
        f"mkdir -p {MODULES_LOAD.parent} {MODPROBE_CONF.parent}",
        f"printf '%s\\n' '# Added by puppetcam setup: the virtual camera' '{MODULE}' > {MODULES_LOAD}",
        f"printf '%s\\n' '# Added by puppetcam setup' {shlex.quote(f'options {MODULE} {OPTIONS}')}"
        f" > {MODPROBE_CONF}",
    ]
    if not st.loaded:
        lines.append(f"modprobe {MODULE}")
    return "\n".join(lines) + "\n"


def elevate(script: str, gui: bool) -> list[str]:
    """How to run the script as root: directly, with sudo in a terminal, or with pkexec."""
    if os.geteuid() == 0:
        return ["sh", "-c", script]
    if not gui and sys.stdin is not None and sys.stdin.isatty() and shutil.which("sudo"):
        return ["sudo", "sh", "-c", script]
    if shutil.which("pkexec"):
        return ["pkexec", "sh", "-c", script]
    if shutil.which("sudo"):
        return ["sudo", "sh", "-c", script]
    raise RuntimeError("Neither sudo nor pkexec found: run puppetcam setup as root.")


def setup_vcam(gui: bool = False, say=print) -> VcamStatus:
    """Make the virtual camera work now and after a reboot. Raises RuntimeError with help."""
    st = status()
    if st.ready and st.persistent:
        say(f"Virtual camera already set up: {', '.join(st.devices)}")
        return st
    steps = []
    if not st.installed:
        steps.append("install the v4l2loopback module")
    steps.append("load it at every boot")
    if not st.loaded:
        steps.append("load it now")
    say("puppetcam needs your password once to " + ", ".join(steps) + ".")
    result = subprocess.run(elevate(root_script(st), gui), capture_output=True, text=True)
    out = (result.stderr or "") + (result.stdout or "")
    if result.returncode != 0:
        if "Key was rejected" in out or "Required key not available" in out:
            raise RuntimeError(SECURE_BOOT)
        if result.returncode in (126, 127) and not out.strip():
            raise RuntimeError("Setup cancelled: the password wasn't given.")
        detail = out.strip().splitlines()[-1] if out.strip() else f"exit code {result.returncode}"
        raise RuntimeError(f"Setup failed: {detail}")
    st = status()
    if not st.ready:
        raise RuntimeError("The module was set up but no virtual camera appeared. "
                           "Restart the computer, then run: puppetcam doctor")
    say(f"Virtual camera ready: {', '.join(st.devices)}. It will come back after a reboot.")
    return st


# --------------------------------------------------------------- menu entry
def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def menu_entry_path() -> Path:
    return _data_home() / "applications" / "puppetcam.desktop"


def icon_path() -> Path:
    return _data_home() / "icons" / "hicolor" / "256x256" / "apps" / "puppetcam.png"


def desktop_entry(run_cmd: list[str], tray_cmd: list[str], icon: Path) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Puppetcam\n"
        "GenericName=Avatar webcam\n"
        "Comment=An animated avatar for your video calls\n"
        f"Exec={shlex.join(run_cmd)}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=AudioVideo;Video;\n"
        "Keywords=webcam;camera;avatar;meeting;zoom;meet;teams;\n"
        "Actions=tray;\n"
        "\n"
        "[Desktop Action tray]\n"
        "Name=Start in the tray (no window)\n"
        f"Exec={shlex.join(tray_cmd)}\n"
    )


def install_menu_entry() -> Path:
    """Add Puppetcam to the applications menu: it opens the avatar window."""
    from .autostart import launch_command
    from .tray import avatar_icon

    tray_cmd = launch_command()
    run_cmd = tray_cmd  # a packaged app: it decides itself
    if tray_cmd[-1] == "tray":  # same Python, `run` instead of `tray`
        run_cmd = [*tray_cmd[:-1], "run", "--notify-errors"]
    icon = icon_path()
    icon.parent.mkdir(parents=True, exist_ok=True)
    avatar_icon(None, size=256).save(icon)
    path = menu_entry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(desktop_entry(run_cmd, tray_cmd, icon), encoding="utf-8")
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(path.parent)], capture_output=True)
    return path


def show_error(message: str, title: str = "puppetcam") -> None:
    """A desktop dialog for errors when there's no terminal to print them to."""
    for cmd in (["zenity", "--error", f"--title={title}", "--no-markup", f"--text={message}"],
                ["kdialog", "--title", title, "--error", message],
                ["notify-send", "-u", "critical", title, message]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, timeout=600)
                return
            except (OSError, subprocess.SubprocessError):
                continue
