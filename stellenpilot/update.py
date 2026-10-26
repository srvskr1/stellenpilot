"""Tell people when a newer Stellenpilot is out and give them the right download.

The app never downloads or runs anything itself: the button opens the installer link in the
browser, and the installer handles the rest (the Windows installer updates an existing install in
place, a Mac user replaces the app in Applications). Links come only from this repository's
releases; anything else in the GitHub answer is ignored.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from . import __version__

REPO = "srvskr1/stellenpilot"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE_PREFIX = f"https://github.com/{REPO}/releases/"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
ASSETS = {"windows": r"Stellenpilot-Setup-{v}\.exe", "mac": r"Stellenpilot-{v}-mac\.dmg"}
CHECK_EVERY = 24 * 3600
CACHE = ".update.json"


def parse(v: str | None) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    return "mac" if sys.platform == "darwin" else "other"


def homebrew(prefix: str | None = None) -> bool:
    """Installed with `brew install`: the formula puts its Python under .../Cellar/stellenpilot/<version>/libexec."""
    return "/Cellar/stellenpilot/" in (sys.prefix if prefix is None else prefix)


def _fetch() -> dict:
    from .http import request_json
    data = request_json(API, timeout=10, retries=0)
    return data if isinstance(data, dict) else {}


def _downloads(release: dict, version: str) -> dict:
    """Installer links of exactly this release, only from this repository."""
    out = {}
    for a in release.get("assets") or []:
        name, url = str((a or {}).get("name") or ""), str((a or {}).get("browser_download_url") or "")
        for os_, pattern in ASSETS.items():
            if re.fullmatch(pattern.format(v=re.escape(version)), name) and url == f"{DOWNLOAD_PREFIX}v{version}/{name}":
                out[os_] = url
    return out


def latest(home: Path, now: float | None = None, fetch=None) -> dict:
    """The newest release, cached for a day so the dashboard asks GitHub at most once a day."""
    now = time.time() if now is None else now
    cache = Path(home) / CACHE
    try:
        old = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    if not isinstance(old, dict):
        old = {}
    if "checked" in old and 0 <= now - float(old["checked"] or 0) < CHECK_EVERY:
        return old
    try:
        rel = (fetch or _fetch)()
    except Exception:  # offline, rate limited: try again tomorrow, keep what we knew
        rel = None
    if rel is None:
        info = {**old, "checked": now}
    else:
        version = str(rel.get("tag_name") or "").lstrip("v")
        ok = bool(parse(version))
        page = str(rel.get("html_url") or "")
        info = {"checked": now, "version": version if ok else "",
                "page": page if page.startswith(PAGE_PREFIX) else PAGE_PREFIX + "latest",
                "downloads": _downloads(rel, version) if ok else {}}
    try:
        cache.write_text(json.dumps(info), encoding="utf-8")
    except OSError:
        pass
    return info


def status(home: Path, enabled: bool = True, current: str = __version__, fetch=None, now: float | None = None) -> dict:
    """What the dashboard banner needs. Never raises."""
    from .launch import frozen
    out = {"current": current, "available": False}
    if not enabled or not parse(current):  # off in Settings, or a development checkout
        return out
    info = latest(home, now, fetch)
    if not (parse(info.get("version")) and parse(info.get("version")) > parse(current)):
        return out
    page = info.get("page") or PAGE_PREFIX + "latest"
    out.update(available=True, latest=info["version"], page=page,
               download=(info.get("downloads") or {}).get(platform()) or page)
    if not frozen():  # a pip, Homebrew or Docker install updates with a command, the app download is the alternative
        from .schedule import in_docker
        exe = sys.executable
        out["command"] = ("docker compose pull && docker compose up -d" if in_docker()
                          else "brew upgrade stellenpilot" if homebrew()
                          else f'"{exe}" -m pip install -U stellenpilot' if " " in exe else f"{exe} -m pip install -U stellenpilot")
    return out
