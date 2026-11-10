"""How to start Stellenpilot again from outside: as `python -m stellenpilot.cli`, or as the Windows app."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import webbrowser


def frozen() -> bool:
    """True inside the Windows app built with PyInstaller (no Python installed)."""
    return bool(getattr(sys, "frozen", False))


def python(exe: str | None = None) -> str:
    """The Python to store in the daily task and desktop icon, one that survives updates.

    Homebrew runs us from .../Cellar/stellenpilot/<version>/libexec and deletes that folder after
    `brew upgrade`. Its .../opt/stellenpilot link always points at the newest version, so use that.
    """
    exe = sys.executable if exe is None else exe
    m = re.match(r"(.*)/Cellar/stellenpilot/[^/]+/(libexec/.*)", exe)
    return f"{m.group(1)}/opt/stellenpilot/{m.group(2)}" if m else exe


def cli_command() -> list[str]:
    """Command prefix that runs the command line, e.g. + ['--home', X, 'run']."""
    return [sys.executable] if frozen() else [python(), "-m", "stellenpilot.cli"]


# Edge or Chrome in app mode (--app=URL) gives the dashboard its own window without tabs or an
# address bar. Edge ships with Windows.
# ponytail: Chromium app mode only; Firefox or Safari only users still get a tab. The real native
# shell is the planned Flutter desktop app.
APP_BROWSERS = (
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "microsoft-edge", "google-chrome", "chromium", "chromium-browser",
)


def open_window(url: str) -> None:
    """Open the dashboard in its own app window, or in a normal browser tab if no Edge or Chrome is found."""
    for candidate in APP_BROWSERS:
        exe = shutil.which(os.path.expandvars(candidate))
        if exe:
            try:
                subprocess.Popen([exe, f"--app={url}"])  # noqa: S603 (fixed list of browsers, local URL)
                return
            except OSError:
                pass
    webbrowser.open(url)
