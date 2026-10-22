"""Tell people when a newer Stellenpilot is out. In the Windows app, install it in one click.

Security model, because this downloads and runs a program:
* The only source is the GitHub API for this repository, over HTTPS. Nothing in the answer can
  point the download anywhere else: the asset name and URL must match fixed patterns.
* The installer is verified against the SHA-256 digest GitHub publishes for the asset before it
  runs. No digest, no one-click install (the banner then links to the release page instead).
* Only a strictly newer version installs. A tampered or replayed answer cannot downgrade the app.
* The file goes into a fresh private temp folder under a fixed name, and runs without a shell.
* pip is never run from the dashboard (see gmail_sync.install_packages): pip installs get the
  command to copy. The Mac app is not notarized, so it gets the download page.
Trust still ends at the GitHub account: whoever controls it can publish a release. Code signing
would close that gap and is the next step once there is a certificate.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from . import __version__

REPO = "srvskr1/stellenpilot"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE_PREFIX = f"https://github.com/{REPO}/releases/"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
SETUP = re.compile(r"Stellenpilot-Setup-(\d+\.\d+\.\d+)\.exe")
DIGEST = re.compile(r"sha256:([0-9a-f]{64})")
MAX_BYTES = 300_000_000  # the installer is about 30 MB; anything far larger is not ours
CHECK_EVERY = 24 * 3600
CACHE = ".update.json"


def parse(v: str | None) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def kind() -> str:
    from .launch import frozen
    from .schedule import in_docker
    if frozen():
        return "windows" if sys.platform.startswith("win") else "mac" if sys.platform == "darwin" else "app"
    return "docker" if in_docker() else "pip"


def _fetch() -> dict:
    from .http import request_json
    data = request_json(API, timeout=10, retries=0)
    return data if isinstance(data, dict) else {}


def _setup_asset(release: dict, version: str) -> dict | None:
    """The Windows installer of exactly this release, if GitHub published a digest for it."""
    for a in release.get("assets") or []:
        if not isinstance(a, dict):
            continue
        m = SETUP.fullmatch(str(a.get("name") or ""))
        url, digest = str(a.get("browser_download_url") or ""), DIGEST.fullmatch(str(a.get("digest") or ""))
        if m and m.group(1) == version and url == f"{DOWNLOAD_PREFIX}v{version}/{a['name']}" and digest:
            return {"url": url, "sha256": digest.group(1), "size": int(a.get("size") or 0)}
    return None


def latest(home: Path, now: float | None = None, fetch=None, force: bool = False) -> dict:
    """The newest release, cached for a day so the dashboard asks GitHub at most once a day."""
    now = time.time() if now is None else now
    fetch = fetch or _fetch
    cache = Path(home) / CACHE
    try:
        old = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    if not force and isinstance(old, dict) and "checked" in old and 0 <= now - float(old["checked"] or 0) < CHECK_EVERY:
        return old
    try:
        rel = fetch()
    except Exception:  # offline, rate limited: try again tomorrow, keep what we knew
        rel = None
    if rel is None:
        info = {**(old if isinstance(old, dict) else {}), "checked": now}
    else:
        version = str(rel.get("tag_name") or "").lstrip("v")
        page = str(rel.get("html_url") or "")
        info = {"checked": now, "version": version if parse(version) else "",
                "page": page if page.startswith(PAGE_PREFIX) else PAGE_PREFIX + "latest",
                "setup": _setup_asset(rel, version) if parse(version) else None}
    try:
        cache.write_text(json.dumps(info), encoding="utf-8")
    except OSError:
        pass
    return info


def status(home: Path, enabled: bool = True, current: str = __version__, fetch=None, now: float | None = None) -> dict:
    """What the dashboard banner needs. Never raises."""
    k = kind()
    out = {"current": current, "kind": k, "available": False}
    if not enabled or not parse(current):  # off in Settings, or a development checkout
        return out
    info = latest(home, now, fetch)
    newer = parse(info.get("version")) and parse(info.get("version")) > parse(current)
    if not newer:
        return out
    out.update(available=True, latest=info["version"], page=info.get("page") or PAGE_PREFIX + "latest",
               oneClick=k == "windows" and bool(info.get("setup")))
    if k == "pip":
        exe = sys.executable
        out["command"] = f'"{exe}" -m pip install -U stellenpilot' if " " in exe else f"{exe} -m pip install -U stellenpilot"
    elif k == "docker":
        out["command"] = "docker compose pull && docker compose up -d"
    return out


def download(setup: dict, dest: Path, opener=None) -> Path:
    """Stream the installer to dest and check its SHA-256. Raises on any mismatch."""
    url = setup["url"]
    if not url.startswith(DOWNLOAD_PREFIX) or not re.fullmatch(r"[0-9a-f]{64}", setup.get("sha256") or ""):
        raise ValueError("refusing an installer that is not from the Stellenpilot releases")
    h, n = hashlib.sha256(), 0
    opener = opener or urllib.request.urlopen
    from .http import USER_AGENT
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener(req, timeout=60) as resp, open(dest, "wb") as f:  # noqa: S310 (https, fixed prefix)
        while chunk := resp.read(1 << 20):
            n += len(chunk)
            if n > MAX_BYTES:
                raise ValueError("installer is larger than expected")
            h.update(chunk)
            f.write(chunk)
    if not hmac.compare_digest(h.hexdigest(), setup["sha256"]):
        dest.unlink(missing_ok=True)
        raise ValueError("installer checksum does not match the release, not installing")
    return dest


def install(home: Path, current: str = __version__) -> str:
    """Windows app only: download, verify and start the silent installer. The installer closes
    this app, replaces it and starts the new version. Returns the version being installed."""
    if kind() != "windows":
        raise ValueError("one click update is only available in the Windows app")
    info = latest(home, force=True)  # always ask GitHub again right before installing
    version, setup = info.get("version"), info.get("setup")
    if not (parse(version) and parse(current) and parse(version) > parse(current)):
        raise ValueError("no newer version to install")
    if not setup:
        raise ValueError("this release has no verified Windows installer, download it from the release page")
    exe = download(setup, Path(tempfile.mkdtemp(prefix="stellenpilot-update-")) / "Stellenpilot-Setup.exe")
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(exe), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/FORCECLOSEAPPLICATIONS"],  # noqa: S603
                     close_fds=True, creationflags=flags)
    return version
