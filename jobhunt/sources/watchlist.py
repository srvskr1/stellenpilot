"""Company watchlist: read the public job feeds of companies you name.

Many companies publish their openings through a hiring system with a free public feed:
Greenhouse, Lever, Ashby, Personio and SmartRecruiters. These feeds are meant to be read by
third parties (no login needed), so this is a clean, legal way to see new roles early,
often before they reach the big job boards.

In config.toml:
    [watch]
    companies = ["greenhouse:trivago", "ashby:deepl", "personio:hornetsecurity"]
Find the right entry from a careers link with:  jobhunt watch <careers page URL>
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from ..http import HttpError, request_json
from ..text import strip_html

NAME = "watchlist"
LABEL = "Company site"
SYSTEMS = ("greenhouse", "lever", "ashby", "personio", "smartrecruiters")
PROBLEMS: list[str] = []  # entries that failed in the last fetch; the pipeline shows them in the run notes
STOP = {"werkstudent", "working", "student", "junior", "senior", "intern", "praktikant", "m/w/d", "and", "und"}


def _text(url: str) -> str:
    import urllib.request
    from ..http import USER_AGENT
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _date(value) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):  # Lever: epoch milliseconds
        return datetime.fromtimestamp(value / 1000, timezone.utc).date().isoformat()
    return str(value)[:10]


# ---------------------------------------------------------------- one function per system

def greenhouse(token: str) -> list[dict]:
    data = request_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "true"})
    out = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name") or ""
        out.append({"id": f"wl-gh-{token}-{j['id']}", "title": j.get("title") or "", "company": j.get("company_name") or token,
                    "location": loc, "remote": "remote" in loc.lower(), "url": j.get("absolute_url") or "",
                    "description": strip_html(html.unescape(j.get("content") or "")),  # content is escaped HTML
                    "posted_at": _date(j.get("first_published") or j.get("updated_at"))})
    return out


def lever(slug: str) -> list[dict]:
    data = None
    for host in ("api.lever.co", "api.eu.lever.co"):  # EU customers live on a separate host
        try:
            data = request_json(f"https://{host}/v0/postings/{slug}", params={"mode": "json"}, retries=0)
            break
        except HttpError as e:
            if e.status != 404:
                raise
    if data is None:
        raise RuntimeError(f"lever:{slug} not found")
    out = []
    for j in data:
        cats = j.get("categories") or {}
        loc = cats.get("location") or ", ".join(cats.get("allLocations") or [])
        lists = "\n".join(f"{x.get('text', '')}\n{strip_html(x.get('content'))}" for x in j.get("lists") or [])
        out.append({"id": f"wl-lv-{slug}-{j['id']}", "title": j.get("text") or "", "company": slug,
                    "location": loc, "remote": j.get("workplaceType") == "remote" or "remote" in loc.lower(),
                    "url": j.get("hostedUrl") or "", "description": (j.get("descriptionPlain") or "") + "\n" + lists,
                    "posted_at": _date(j.get("createdAt"))})
    return out


def ashby(name: str) -> list[dict]:
    data = request_json(f"https://api.ashbyhq.com/posting-api/job-board/{name}")
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        loc = ", ".join(x for x in [j.get("location"), *[(s or {}).get("location", "") for s in j.get("secondaryLocations") or []]] if x)
        out.append({"id": f"wl-ab-{name}-{j['id']}", "title": j.get("title") or "", "company": name,
                    "location": loc, "remote": bool(j.get("isRemote")) or j.get("workplaceType") == "Remote",
                    "url": j.get("jobUrl") or "", "description": j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")),
                    "posted_at": _date(j.get("publishedAt"))})
    return out


def personio(company: str) -> list[dict]:
    xml = _text(f"https://{company}.jobs.personio.de/xml?language=en")
    if "<!ENTITY" in xml or "<!DOCTYPE" in xml:  # a job feed never needs these; refusing them blocks entity bombs
        raise RuntimeError(f"personio:{company} sent an unexpected XML document")
    root = ET.fromstring(xml)
    out = []
    for p in root.iter("position"):
        get = lambda tag: (p.findtext(tag) or "").strip()  # noqa: E731
        offices = [get("office")] + [o.text or "" for o in p.findall("additionalOffices/office")]
        loc = ", ".join(o for o in offices if o)
        desc = "\n".join(f"{d.findtext('name') or ''}\n{strip_html(d.findtext('value'))}" for d in p.findall("jobDescriptions/jobDescription"))
        out.append({"id": f"wl-ps-{company}-{get('id')}", "title": get("name"), "company": get("subcompany") or company,
                    "location": loc, "remote": "remote" in loc.lower(),
                    "url": f"https://{company}.jobs.personio.de/job/{get('id')}", "description": desc,
                    "posted_at": _date(get("createdAt"))})
    return out


def smartrecruiters(identifier: str, country: str = "") -> list[dict]:
    base = f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings"
    data = request_json(base, params={"limit": 100, "country": country.lower() or None})
    out = []
    for j in data.get("content", []):
        loc = (j.get("location") or {})
        out.append({"id": f"wl-sr-{identifier}-{j['id']}", "title": j.get("name") or "",
                    "company": (j.get("company") or {}).get("name") or identifier,
                    "location": loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
                    "remote": bool(loc.get("remote")), "url": f"https://jobs.smartrecruiters.com/{identifier}/{j['id']}",
                    "description": "", "posted_at": _date(j.get("releasedDate")), "_detail": j.get("ref")})
    return out


def _sr_description(job: dict) -> None:
    if job.get("_detail"):
        try:
            d = request_json(job["_detail"])
            secs = (d.get("jobAd") or {}).get("sections") or {}
            job["description"] = "\n".join(strip_html((secs.get(k) or {}).get("text")) for k in ("jobDescription", "qualifications", "additionalInformation"))
            job["url"] = d.get("postingUrl") or job["url"]
        except Exception:  # timeout or odd answer: keep the job, just without the full text
            pass
    job.pop("_detail", None)


# ---------------------------------------------------------------- helpers

def parse_careers_url(url: str) -> str | None:
    """Turn a careers page link into a watchlist entry like 'greenhouse:trivago'."""
    rules = [
        (r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)", "greenhouse"),
        (r"[?&]for=([\w-]+)", "greenhouse"),
        (r"jobs(?:\.eu)?\.lever\.co/([\w.-]+)", "lever"),
        (r"jobs\.ashbyhq\.com/([\w.%-]+)", "ashby"),
        (r"([\w-]+)\.jobs\.personio\.(?:de|com)", "personio"),
        (r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)", "smartrecruiters"),
    ]
    for rx, system in rules:
        m = re.search(rx, url or "", re.I)
        if m:
            return f"{system}:{m.group(1)}"
    return None


def title_rules(settings) -> list[list[str]]:
    """Each rule is a list of words that must ALL be in the title; any rule may match.
    From [watch] title_words (each word is its own rule) or from search.keywords minus filler words,
    so "Junior Data Engineer" needs both "data" and "engineer"."""
    w = settings["watch"].get("title_words") or []
    if w:
        return [[x.lower()] for x in w]
    rules = []
    for kw in settings["search"]["keywords"]:
        words = [x.lower() for x in kw.split() if x.lower() not in STOP]
        if words and words not in rules:
            rules.append(words)
    return rules or [["data"]]


def title_matches(title: str, rules: list[list[str]]) -> bool:
    t = (title or "").lower()
    return any(all(w in t for w in rule) for rule in rules)


def _place_ok(job: dict, settings) -> bool:
    places = settings["watch"].get("locations")
    if places is None:
        s = settings["search"]
        places = [s["city"], *s.get("nearby_cities", []), "remote", *COUNTRY_WORDS.get(s["country"].lower(), [])]
    loc = (job.get("location") or "").lower()
    return not loc or job.get("remote") or any(p.lower() in loc for p in places)


COUNTRY_WORDS = {"de": ["germany", "deutschland"], "at": ["austria", "österreich"], "ch": ["switzerland", "schweiz"],
                 "nl": ["netherlands", "nederland"], "gb": ["united kingdom", "uk", "england"], "us": ["united states", "usa"]}


def fetch_company(entry: str, country: str = "") -> list[dict]:
    system, _, slug = entry.partition(":")
    system = system.strip().lower()
    if system not in SYSTEMS or not slug.strip():
        raise RuntimeError(f"bad watchlist entry '{entry}', use one of {', '.join(SYSTEMS)} like 'greenhouse:trivago'")
    slug = slug.strip()
    if system == "smartrecruiters":
        return smartrecruiters(slug, country)
    return {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "personio": personio}[system](slug)


def fetch(settings) -> list[dict]:
    from . import job_type_from_title
    w = settings["watch"]
    rules = title_rules(settings)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(w.get("max_age_days", 30)))).date().isoformat()
    out, problems = [], []
    PROBLEMS.clear()
    for entry in w.get("companies") or []:
        try:
            jobs = fetch_company(entry, settings["search"]["country"])
        except Exception as e:
            problems.append(f"{entry}: {e}")
            continue
        for j in jobs:
            if not title_matches(j["title"], rules):
                continue
            if j["posted_at"] and j["posted_at"] < cutoff:
                continue
            if not _place_ok(j, settings):
                continue
            if "_detail" in j:
                _sr_description(j)
            out.append({**j, "source": LABEL, "job_type": job_type_from_title(j["title"])})
    PROBLEMS.extend(problems)
    if problems and not out:
        raise RuntimeError("; ".join(problems))
    return out
