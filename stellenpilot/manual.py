"""Add a job yourself: from a link to a company careers page, or from pasted ad text.

Sites whose terms forbid automated access (LinkedIn, StepStone, Indeed, XING, Glassdoor) are
never fetched. Paste the ad text instead; that is you reading the page, not a bot.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import urllib.parse
import urllib.request

from .http import USER_AGENT
from .text import dedupe_key, strip_html
from .llm import job_ad

# Sites whose terms forbid automated access. Matched against the host, on the first link and every redirect.
NO_FETCH = ("linkedin.com", "lnkd.in", "stepstone.", "indeed.", "xing.com", "glassdoor.")
SOURCE = "Added by you"
MAX_PAGE_BYTES = 3_000_000


class AddError(RuntimeError):
    pass


def _public(ip: ipaddress._BaseAddress) -> bool:
    """Only addresses on the public internet. IPv4 written as IPv6 (::ffff:127.0.0.1) is judged as IPv4."""
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return ip.is_global and not ip.is_multicast


def resolve_public(url: str) -> tuple[str, str, int, str]:
    """Check a link and look its host up ONCE. Returns (scheme, host, port, ip). The caller must connect
    to exactly this ip: looking the name up again later could give a different, internal address
    (DNS rebinding), and the check would mean nothing.
    Refuses anything but http(s), sites that forbid automated access, and every non public address."""
    parts = urllib.parse.urlsplit((url or "").strip())
    scheme, host = parts.scheme.lower(), (parts.hostname or "").lower()
    if scheme not in ("http", "https") or not host:
        raise AddError("The link must start with http:// or https://")
    if any(b in host for b in NO_FETCH):
        raise AddError(f"{host} does not allow automated access. Open the ad, copy its text, and add it with "
                       "--text (or paste it into the dashboard), plus --title and --company.")
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError:
        raise AddError("The link has an invalid port.") from None
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        # No proxy fallback on purpose: a proxy (often a company proxy) can reach internal hosts we
        # cannot check, so a name that does not resolve here is not fetched at all.
        raise AddError(f"Could not find {host} from this computer. Check the link, or copy the ad text "
                       "and add it as text instead.") from None
    addrs = [info[4][0] for info in infos]
    for a in addrs:
        if not _public(ipaddress.ip_address(a.split("%")[0])):
            raise AddError(f"{host} points to a local or private network address. Only public job pages can be added by link.")
    if not addrs:
        raise AddError(f"Could not find {host}. Check the link.")
    return scheme, host, port, addrs[0]


def check_url(url: str) -> str:
    """Kept for callers that only want the check. Fetching must go through open_public()."""
    resolve_public(url)
    return url


class _PinnedHTTP(http.client.HTTPConnection):
    """Talks to the checked address only; the Host header still names the site."""
    def __init__(self, host: str, ip: str, port: int, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    """Connects to the checked address, and still verifies the certificate for the site's name (SNI)."""
    def __init__(self, host: str, ip: str, port: int, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class FetchError(RuntimeError):
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status


def open_public(url: str, max_bytes: int = MAX_PAGE_BYTES, timeout: float = 30, max_redirects: int = 5) -> tuple[str, bytes]:
    """GET a public web page. Every hop (the link and each redirect) is checked and connected to by
    its checked address, never through a proxy and never by a second name lookup. Returns
    (final url, body). Raises AddError for refused links and FetchError for HTTP errors."""
    for _ in range(max_redirects + 1):
        scheme, host, port, ip = resolve_public(url)
        parts = urllib.parse.urlsplit(url)
        path = urllib.parse.urlunsplit(("", "", parts.path or "/", parts.query, ""))
        conn = (_PinnedHTTPS if scheme == "https" else _PinnedHTTP)(host, ip, port, timeout)
        try:
            default = 443 if scheme == "https" else 80
            conn.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": "text/html",
                                               "Host": host if port == default else f"{host}:{port}"})
            resp = conn.getresponse()
            if resp.status in (301, 302, 303, 307, 308) and resp.getheader("Location"):
                url = urllib.parse.urljoin(url, resp.getheader("Location"))
                continue
            if resp.status >= 400:
                raise FetchError(resp.status, url)
            return url, resp.read(max_bytes)
        finally:
            conn.close()
    raise AddError("The link redirects too often.")


def fetch_page(url: str) -> str:
    return open_public(url)[1].decode("utf-8", "replace")


def job_from_feed(url: str, country: str = "") -> dict:
    """Job links on Greenhouse, Lever, Ashby, Personio or SmartRecruiters: read the job from the
    company's public feed, which is cleaner than the web page and meant for third parties."""
    from .sources.watchlist import fetch_company, parse_careers_url
    entry = parse_careers_url(url)
    tail = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    if entry and entry.startswith("smartrecruiters:"):
        # Links look like /Company/744000154685394-job-title-slug; read that one posting directly.
        m = re.match(r"(\d{6,})", tail)
        return _smartrecruiters_job(entry.split(":", 1)[1], m.group(1)) if m else {}
    if not entry or not re.fullmatch(r"[\w-]{4,}", tail):
        return {}
    try:
        jobs = fetch_company(entry, country)
    except Exception:
        return {}
    for j in jobs:
        if j["id"].endswith("-" + tail):
            j.pop("_detail", None)
            return j
    return {}


def _smartrecruiters_job(company: str, posting_id: str) -> dict:
    from .http import request_json
    from .sources.watchlist import _sr_description
    try:
        d = request_json(f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{posting_id}", retries=0)
        if not isinstance(d, dict):
            return {}
    except Exception:
        return {}
    loc = d.get("location") or {}
    job = {"id": f"wl-sr-{company}-{posting_id}", "title": d.get("name") or "",
           "company": (d.get("company") or {}).get("name") or company,
           "location": loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
           "remote": bool(loc.get("remote")), "url": d.get("postingUrl") or "",
           "description": "", "posted_at": (d.get("releasedDate") or "")[:10],
           "_detail": f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{posting_id}"}
    _sr_description(job)
    return job


def _txt(v) -> str:
    """schema.org values may be text, a list, or an object with a name; always return plain text."""
    if isinstance(v, list):
        return ", ".join(t for t in (_txt(x) for x in v) if t)
    if isinstance(v, dict):
        return _txt(v.get("name") or v.get("@value") or "")
    return strip_html(str(v)) if v not in (None, "") else ""


def _place(loc) -> str:
    if not isinstance(loc, dict):
        return _txt(loc)
    addr = loc.get("address")
    if isinstance(addr, dict):
        return _txt(addr.get("addressLocality") or addr.get("addressRegion") or addr.get("addressCountry"))
    return _txt(addr or loc.get("name"))


def job_from_jsonld(page: str) -> dict:
    """Most career sites embed a schema.org JobPosting for Google. Use it when present.
    Never raises: odd markup just means falling back to the page text."""
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(block.strip())
            items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
            for it in items if isinstance(items, list) else []:
                if not isinstance(it, dict) or "JobPosting" not in str(it.get("@type")):
                    continue
                locs = it.get("jobLocation") or []
                locs = locs if isinstance(locs, list) else [locs]
                place = ", ".join(dict.fromkeys(p for p in (_place(l) for l in locs) if p))
                remote = "TELECOMMUTE" in str(it.get("jobLocationType", "")).upper()
                return {"title": _txt(it.get("title")), "company": _txt(it.get("hiringOrganization")),
                        "location": ("Remote, " if remote else "") + place, "remote": remote,
                        "description": _txt(it.get("description")), "posted_at": str(it.get("datePosted") or "")[:10]}
        except (ValueError, TypeError, AttributeError):
            continue
    return {}


def _guess_with_llm(llm, text: str) -> dict:
    try:
        out = llm.complete_json("Extract facts from a job ad. Return JSON with keys title, company, location. Use \"\" when unknown.",
                                job_ad(text, 4000), max_tokens=200)
    except Exception:  # model down or broken JSON: the user can still type title and company
        return {"title": "", "company": "", "location": ""}
    return {k: _txt(out.get(k)).strip() for k in ("title", "company", "location")}


def build_job(*, url: str = "", text: str = "", title: str = "", company: str = "", location: str = "", llm=None) -> dict:
    info: dict = {}
    url = (url or "").strip()
    if url and not urllib.parse.urlsplit(url).scheme.lower() in ("http", "https"):
        raise AddError("The link must start with http:// or https://")
    if url and not text:
        info = job_from_feed(url)
        if not info:
            try:
                page = fetch_page(url)
            except AddError:
                raise
            except Exception as e:
                raise AddError(f"Could not open the page ({e}). Copy the ad text and add it with --text "
                               "(or paste it into the dashboard).") from None
            info = job_from_jsonld(page)
            if not info.get("description"):
                info["description"] = strip_html(page)
                m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
                info.setdefault("title", strip_html(m.group(1)) if m else "")
    elif text:
        info["description"] = text.strip()
    if not info.get("description"):
        raise AddError("Give a link to the ad or paste its text.")
    # explicit arguments win, then structured data, then the LLM
    job = {"title": title or info.get("title", ""), "company": company or info.get("company", ""),
           "location": location or info.get("location", ""), "remote": bool(info.get("remote")) or "remote" in location.lower(),
           "description": info["description"][:20000], "posted_at": info.get("posted_at", ""), "url": url}
    if (not job["title"] or not job["company"]) and llm and llm.enabled:
        guess = _guess_with_llm(llm, job["description"])
        for k in ("title", "company", "location"):
            job[k] = job[k] or guess[k]
    if not job["title"] or not job["company"]:
        raise AddError("Could not tell the job title and company. Add them with --title and --company "
                       "(or the fields in the dashboard).")
    key = url or job["description"]
    job.update({"id": "me-" + hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:12], "source": SOURCE,
                "dedupe_key": dedupe_key(job["company"], job["title"])})
    return job


def add_job(settings, db, *, tailor: bool = False, **kw) -> dict:
    """Build, score and store a job. Returns {"job": ..., "status": "added"|"exists", "tailored": {...}}."""
    from .llm import LLM
    from .pipeline import my_german_level
    from .score import score_job, taste_summary
    from .sources import job_type_from_title
    llm = LLM(settings)
    job = build_job(llm=llm, **kw)
    from .pipeline import repost_since
    since = repost_since(settings) or "0000-00-00"
    existing = db.job(job["id"]) or next(iter(db.jobs("dedupe_key = ? AND found_at >= ?", (job["dedupe_key"], since))), None)
    if existing:
        return {"job": existing, "status": "exists"}
    job["job_type"] = job_type_from_title(job["title"])
    lang = settings["language"]
    job.update(score_job(job, settings.profile, llm, taste_summary(db.jobs("rating IS NOT NULL")),
                         skip_german=False,  # you chose this job yourself, so it is never auto skipped
                         my_german=my_german_level(settings), tolerance=int(lang.get("german_tolerance", 1))))
    job["status_source"] = "manual"
    db.insert_job(job)
    result = {"job": db.job(job["id"]), "status": "added"}
    if tailor:
        result["tailored"] = make_docs(settings, db, job["id"], llm)
        result["job"] = db.job(job["id"])
    return result


def make_docs(settings, db, job_id: str, llm=None) -> dict:
    """Write the tailored CV and cover letter for one stored job and mark it ready."""
    from pathlib import Path
    from .llm import LLM
    from .pipeline import my_german_level
    from .tailor import tailor_job
    job = db.job(job_id)
    if not job:
        raise AddError("Unknown job")
    t = settings["tailor"]
    res = tailor_job(job, settings.profile, (Path(settings.home) / t["output_dir"]).resolve(), llm or LLM(settings),
                     t.get("make_pdf", True), t.get("letter_language", "auto"), my_german_level(settings))
    db.mark_ready(job_id, res["folder"], f"Your experience shows {res['coverage']}% of the tools the ad names")
    return res
