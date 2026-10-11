"""Remotive remote jobs API. Free and keyless: https://remotive.com/api-documentation

Their terms: link back to the job's Remotive URL and name Remotive as the source (the dashboard
labels every Remotive job with a linked "Remotive" tag), do not resubmit the jobs to other job sites,
and call the API at most about 4 times a day. This module makes ONE call per run.
The free feed is small (often a few dozen jobs) and delayed by 24 hours.
Remote roles only, so this source is used when include_remote is on.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..http import request_json
from ..text import strip_html, title_excluded

NAME = "remotive"
LABEL = "Remotive"
URL = "https://remotive.com/api/remote-jobs"
# Location words that mean "open to someone living in Europe".
OPEN_TO = ("worldwide", "anywhere", "europe", "emea", "cet", "cest")
COUNTRY_WORDS = {"de": ("germany", "deutschland"), "at": ("austria",), "ch": ("switzerland",), "nl": ("netherlands",),
                 "fr": ("france",), "es": ("spain",), "it": ("italy",), "pl": ("poland",), "gb": ("uk", "united kingdom"),
                 "ie": ("ireland",), "us": ("usa", "united states"), "ca": ("canada",)}


def open_to(location: str, country: str) -> bool:
    loc = (location or "worldwide").lower()
    return any(w in loc for w in OPEN_TO + COUNTRY_WORDS.get(country, ()))


def fetch(settings) -> list[dict]:
    from . import job_type_from_title, title_has_keyword

    s = settings["search"]
    if not s.get("include_remote"):
        return []
    country = s["country"].lower()
    cutoff = (datetime.now() - timedelta(days=int(s["max_age_days"]) + 1)).date().isoformat()  # +1: feed is a day late
    out = []
    for j in request_json(URL).get("jobs") or []:  # one call: the whole free feed
        title = j.get("title") or ""
        if not title_has_keyword(title, s["keywords"]) or title_excluded(title, s.get("exclude_title_words", [])):
            continue
        if not open_to(j.get("candidate_required_location"), country) or (j.get("publication_date") or "")[:10] < cutoff:
            continue
        out.append({
            "id": f"rm-{j.get('id')}",
            "source": LABEL,
            "title": title,
            "company": j.get("company_name") or "",
            "location": f"Remote, {j.get('candidate_required_location') or 'Worldwide'}",
            "remote": True,
            "url": j.get("url") or "",
            "description": strip_html(j.get("description")),
            "posted_at": (j.get("publication_date") or "")[:10],
            "job_type": job_type_from_title(title, {"full_time": "Full time", "part_time": "Part time"}.get(j.get("job_type") or "", "")),
        })
    return out
