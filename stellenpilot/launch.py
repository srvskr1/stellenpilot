"""How to start Stellenpilot again from outside: as `python -m stellenpilot.cli`, or as the Windows app."""
from __future__ import annotations

import re
import sys


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
