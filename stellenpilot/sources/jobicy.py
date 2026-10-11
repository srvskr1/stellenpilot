"""Jobicy remote jobs API. Free and keyless: https://jobicy.com/jobs-rss-feed

Their terms: credit Jobicy with a clickable link to the original listing (the dashboard labels
every Jobicy job with a linked "Jobicy" tag and links to the Jobicy page), never present the
listings as your own, and start an automated pass at most once an hour (a daily run is far below).
Their site blocks bursts of calls, so this module makes few calls (one region at a time, a pause
between calls) and keeps what it already has if it gets blocked. Listings cover the last 7 days. Remote roles only, so this source is used when include_remote is on.
"""
from __future__ import annotations

import time

from ..http import HttpError, request_json
from ..text import strip_html, title_excluded

NAME = "jobicy"
LABEL = "Jobicy"
URL = "https://jobicy.com/api/v2/remote-jobs"
# Jobicy region slugs for the search country; "europe" and "emea" roles are open to people in Europe.
GEO = {"de": "germany", "at": "austria", "ch": "switzerland", "nl": "netherlands", "be": "belgium",
       "fr": "france", "es": "spain", "it": "italy", "pl": "poland", "gb": "uk", "ie": "ireland",
       "us": "usa", "ca": "canada", "au": "australia"}
PAUSE = 3  # seconds between calls
EUROPE = {"de", "at", "ch", "nl", "be", "fr", "es", "it", "pl", "gb", "ie"}


def _geos(country: str) -> list[str]:
    geos = [GEO[country]] if country in GEO else []
    return geos + (["europe"] if country in EUROPE else [])


def fetch(settings) -> list[dict]:
    from . import job_type_from_title, title_has_keyword

    s = settings["search"]
    if not s.get("include_remote"):
        return []
    pages = int(settings["sources"]["limits"].get("jobicy_pages", 2))
    seen, out, calls = set(), [], 0
    for geo in _geos(s["country"].lower()):
        params = {"count": 200, "geo": geo}
        for _ in range(pages):
            if calls:
                time.sleep(PAUSE)
            calls += 1
            try:
                data = request_json(URL, params=params, retries=0)
            except HttpError as e:
                if e.status in (403, 429):  # rate limited: keep what we have, try again next run
                    return out
                raise
            for j in data.get("jobs") or []:
                jid, title = str(j.get("id") or ""), j.get("jobTitle") or ""
                if not jid or jid in seen or not title_has_keyword(title, s["keywords"]) \
                        or title_excluded(title, s.get("exclude_title_words", [])):
                    continue
                seen.add(jid)
                types = j.get("jobType") or []
                types = " ".join(types if isinstance(types, list) else [str(types)]).lower()
                out.append({
                    "id": f"jc-{jid}",
                    "source": LABEL,
                    "title": strip_html(title),
                    "company": j.get("companyName") or "",
                    "location": f"Remote, {j.get('jobGeo') or 'anywhere'}",
                    "remote": True,
                    "url": j.get("url") or "",
                    "description": strip_html(j.get("jobDescription") or j.get("jobExcerpt") or ""),
                    "posted_at": (j.get("pubDate") or "")[:10],
                    "job_type": job_type_from_title(title, "Part time" if "part" in types else "Full time" if "full" in types else ""),
                })
            cursor = data.get("nextCursor")
            if str(data.get("hasMore")).lower() != "true" or not cursor:
                break
            params = {"count": 200, "geo": geo, "cursor": cursor}
    return out
