"""Add a job yourself: from a link to a company careers page, or from pasted ad text.

Sites whose terms forbid automated access (LinkedIn, StepStone, Indeed, XING, Glassdoor) are
never fetched. Paste the ad text instead; that is you reading the page, not a bot.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
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


def check_url(url: str) -> str:
    """Refuse anything but a public http(s) page: no file:, no local or private network addresses,
    no sites that forbid automated access. Used for the first link and again for every redirect."""
    parts = urllib.parse.urlsplit((url or "").strip())
    scheme, host = parts.scheme.lower(), (parts.hostname or "").lower()
    if scheme not in ("http", "https") or not host:
        raise AddError("The link must start with http:// or https://")
    if any(b in host for b in NO_FETCH):
        raise AddError(f"{host} does not allow automated access. Open the ad, copy its text, and add it with "
                       "--text (or paste it into the dashboard), plus --title and --company.")
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        try:  # a literal IP address needs no lookup
            addrs = {str(ipaddress.ip_address(host.strip("[]")))}
        except ValueError:
            if urllib.request.getproxies().get(scheme):
                return url  # behind a proxy the name may only resolve there; the proxy reaches public sites only
            raise AddError(f"Could not find {host}. Check the link.") from None
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise AddError(f"{host} points to a local or private network address. Only public job pages can be added by link.")
    return url


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_CheckedRedirects)


def fetch_page(url: str) -> str:
    check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with _OPENER.open(req, timeout=30) as r:
        return r.read(MAX_PAGE_BYTES).decode("utf-8", "replace")


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
