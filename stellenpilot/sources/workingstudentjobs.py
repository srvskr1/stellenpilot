"""workingstudentjobs.de API (Werkstudent and internship roles in Germany).

Free and keyless, 60 requests a minute. Docs: https://www.workingstudentjobs.de/developers
Terms: link every job with its url or apply_url (we use apply_url, it counts the click for
the employer) and do not re-host the listings. The feed has no ad text, so the description
is built from its skills, language and field values.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..http import HttpError, request_json

NAME = "workingstudentjobs"
COUNTRIES = {"de"}
LABEL = "workingstudentjobs.de"
URL = "https://www.workingstudentjobs.de/api/v1/jobs"
MAX_PAGES = 3  # 300 jobs per page per city; with `since` one page is usually enough
PROBLEMS: list[str] = []


def _job(j: dict, types_hint: str) -> dict:
    from . import job_type_from_title

    loc = j.get("location") or {}
    langs = j.get("languages") or {}
    desc = " ".join(filter(None, [
        "Skills: " + ", ".join(j["skills"]) + "." if j.get("skills") else "",
        " ".join(f"{k.capitalize()}: {v}." for k, v in langs.items() if v),
        f"Field: {j['field']}." if j.get("field") else "",
    ]))
    remote = j.get("working_mode") == "remote"
    return {
        "id": f"wsj-{j['id']}",
        "source": LABEL,
        "title": j["title"],
        "company": (j.get("company") or {}).get("name") or "",
        "location": ("Remote, " if remote else "") + (loc.get("city") or ""),
        "remote": remote,
        "url": j.get("apply_url") or j.get("url") or "",
        "description": desc,
        "posted_at": (j.get("posted_at") or "")[:10],
        "job_type": job_type_from_title(j["title"], "Werkstudent" if "working_student" in types_hint else ""),
    }


def fetch(settings) -> list[dict]:
    from . import title_has_keyword

    PROBLEMS.clear()
    s = settings["search"]
    since = (datetime.now(timezone.utc).date() - timedelta(days=int(s["max_age_days"]))).isoformat()
    pages = int(settings["sources"]["limits"].get("workingstudentjobs_pages", MAX_PAGES))
    out, seen = [], set()
    # One call per city, so an unknown city (their API answers 400) skips only that city.
    for city in dict.fromkeys(c.strip().lower().replace(" ", "-") for c in [s["city"], *s.get("nearby_cities", [])] if c.strip()):
        url, params = URL, {"city": city, "since": since, "limit": 300, "ref": "stellenpilot"}
        for _ in range(pages):
            try:
                data = request_json(url, params=params)
            except HttpError as e:
                if e.status != 400:
                    raise
                PROBLEMS.append(f"city '{city}' is not known to workingstudentjobs.de")
                break
            for j in data.get("data") or []:
                if j.get("id") and j.get("title") and j["id"] not in seen and title_has_keyword(j["title"], s["keywords"]):
                    seen.add(j["id"])
                    out.append(_job(j, " ".join(j.get("types") or [])))
            url, params = (data.get("links") or {}).get("next"), None  # the next link carries the query
            if not url:
                break
    return out
