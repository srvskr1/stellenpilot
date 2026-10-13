"""How to start Stellenpilot again from outside: as `python -m stellenpilot.cli`, or as the Windows app."""
from __future__ import annotations

import sys


def frozen() -> bool:
    """True inside the Windows app built with PyInstaller (no Python installed)."""
    return bool(getattr(sys, "frozen", False))


def cli_command() -> list[str]:
    """Command prefix that runs the command line, e.g. + ['--home', X, 'run']."""
    return [sys.executable] if frozen() else [sys.executable, "-m", "stellenpilot.cli"]
