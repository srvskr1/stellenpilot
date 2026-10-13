"""A desktop icon that starts Stellenpilot for this workspace and opens it in the browser.

Windows: a normal shortcut (.lnk) on the desktop. macOS: Stellenpilot.command on the desktop.
Linux: a menu entry plus a copy on the desktop if there is one. Each one runs this same Python
with `-m stellenpilot serve --home <workspace>`, so no terminal commands are needed afterwards.
"""
from __future__ import annotations

import functools
import os
import subprocess
import sys
from importlib import resources
from pathlib import Path

NAME = "Stellenpilot"


def _icon(ext: str) -> str:
    return str(resources.files("stellenpilot") / "web" / f"icon.{ext}")


def _python() -> str:
    exe = Path(sys.executable)
    return str(exe)


def _ps(script: str) -> str:
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout or "PowerShell failed").strip()[-300:])
    return out.stdout.strip()


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"  # PowerShell single quoted string


@functools.lru_cache(maxsize=1)
def desktop_dir() -> Path:
    if sys.platform.startswith("win"):
        try:  # follows OneDrive and renamed desktops
            return Path(_ps("[Environment]::GetFolderPath('Desktop')"))
        except Exception:
            pass
    return Path.home() / "Desktop"


def create(home: Path) -> Path:
    """Create or update the icon for the workspace `home`. Returns where it was put."""
    home = Path(home).resolve()
    args = ["-m", "stellenpilot", "serve", "--home", str(home)]
    if sys.platform.startswith("win"):
        target = desktop_dir() / f"{NAME}.lnk"
        arg_line = " ".join(f'"{a}"' if " " in a else a for a in args)
        _ps(f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({_q(str(target))});"
            f"$s.TargetPath={_q(_python())};$s.Arguments={_q(arg_line)};"
            f"$s.WorkingDirectory={_q(str(home))};$s.IconLocation={_q(_icon('ico'))};"
            f"$s.WindowStyle=7;$s.Description='Start Stellenpilot, your local AI job assistant';$s.Save()")
        return target
    if sys.platform == "darwin":
        target = desktop_dir() / f"{NAME}.command"
        target.parent.mkdir(parents=True, exist_ok=True)
        cmd = " ".join(_sh(a) for a in [_python(), *args])
        target.write_text(f"#!/bin/sh\n# Starts Stellenpilot. Keep this window open while you use it.\ncd {_sh(str(home))}\nexec {cmd}\n",
                          encoding="utf-8")
        target.chmod(0o755)
        return target
    entry = ("[Desktop Entry]\nType=Application\nName=Stellenpilot\nComment=Your local AI job assistant\n"
             f"Exec={' '.join(_desk(a) for a in [_python(), *args])}\nPath={home}\nIcon={_icon('png')}\n"
             "Terminal=true\nCategories=Office;\n")
    apps = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    target = apps / "stellenpilot.desktop"
    target.write_text(entry, encoding="utf-8")
    target.chmod(0o755)
    desk = desktop_dir()
    if desk.is_dir():
        copy = desk / "stellenpilot.desktop"
        copy.write_text(entry, encoding="utf-8")
        copy.chmod(0o755)
        return copy
    return target


def exists() -> bool:
    if sys.platform.startswith("win"):
        return (desktop_dir() / f"{NAME}.lnk").exists()
    if sys.platform == "darwin":
        return (desktop_dir() / f"{NAME}.command").exists()
    apps = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "applications"
    return (apps / "stellenpilot.desktop").exists()


def _sh(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def _desk(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"' if any(c in s for c in ' "\\') else s
