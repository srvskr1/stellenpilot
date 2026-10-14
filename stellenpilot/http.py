"""Tiny JSON over HTTP helper on the standard library, with retries on 429 and 5xx."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

USER_AGENT = f"stellenpilot/{__version__} (+https://github.com/srvskr1/stellenpilot)"


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status


def request_json(url: str, *, params: dict | None = None, headers: dict | None = None,
                 body: dict | None = None, method: str | None = None,
                 timeout: float = 30, retries: int = 2) -> dict | list:
    if params:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(clean, doseq=True)
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    if data is not None:
        hdrs.setdefault("Content-Type", "application/json")
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise HttpError(e.code, text) from None
        except urllib.error.URLError:
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def stream_lines(url: str, *, headers: dict | None = None, body: dict | None = None, timeout: float = 600):
    """POST JSON and yield the response line by line as it arrives (server sent events or NDJSON).
    Used to show live progress while a model on this computer writes a long answer."""
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"User-Agent": USER_AGENT, "Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.read().decode("utf-8", "replace")) from None
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if line:
                yield line


def friendly_error(e: Exception) -> str:
    """Plain words for network errors, so people know what to check."""
    text = str(e)
    low = text.lower()
    if "getaddrinfo" in low or "name or service not known" in low or "nodename nor servname" in low or "11001" in low:
        return "no internet: could not look up the website address. Check your connection, VPN or proxy"
    if "timed out" in low or "timeout" in low:
        return "the website did not answer in time. Try again later"
    if "certificate" in low or "ssl" in low:
        return "secure connection failed (often an antivirus or company proxy checking traffic)"
    if "connection refused" in low or "10061" in low:
        return "connection refused. A firewall may be blocking Python"
    return text

