"""Tiny JSON over HTTP helper on the standard library, with retries on 429 and 5xx."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "stellenpilot/0.1 (+https://github.com/srvskr1/stellenpilot)"


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
