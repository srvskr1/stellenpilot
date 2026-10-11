"""Arbeitnow job board API (Germany, many English speaking roles).

Free and keyless. Their terms ask for a link back to https://www.arbeitnow.com ,
which the dashboard shows on every Arbeitnow job and in its footer.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..http import request_json
from ..text import strip_html

NAME = "arbeitnow"
COUNTRIES = {"de"}
LABEL = "Arbeitnow"
URL = "https://www.arbeitnow.com/api/job-board-api"
MAX_PAGES = 10  # 325 jobs per page, newest first; stops early at max_age_days


def fetch(settings) -> list[dict]:
    from . import job_type_from_title, title_has_keyword

    s = settings["search"]
    places = [p.lower() for p in [s["city"], *s.get("nearby_cities", [])]]
    cutoff = datetime.now(timezone.utc).timestamp() - int(s["max_age_days"]) * 86400
    out = []
    for page in range(1, int(settings["sources"]["limits"].get("arbeitnow_pages", MAX_PAGES)) + 1):
        data = request_json(URL, params={"page": page})
        items = data.get("data") or []
        for j in items:
            if not j.get("slug") or not j.get("title"):
                continue
            if (j.get("created_at") or 0) < cutoff:
                return out
            remote = bool(j.get("remote"))
            here = any(p in (j.get("location") or "").lower() for p in places)
            if not (here or (remote and s.get("include_remote"))):
                continue
            if not title_has_keyword(j.get("title"), s["keywords"]):
                continue
            types = " ".join(t for t in (j.get("job_types") or []) if t).lower()
            out.append({
                "id": f"an-{j['slug']}",
                "source": LABEL,
                "title": j.get("title", ""),
                "company": j.get("company_name") or "",
                "location": ("Remote, " if remote else "") + (j.get("location") or ""),
                "remote": remote,
                "url": j.get("url") or "",
                "description": strip_html(j.get("description")),
                "posted_at": datetime.fromtimestamp(j["created_at"], timezone.utc).date().isoformat(),
                "job_type": job_type_from_title(j.get("title", ""), "Werkstudent" if "student" in types else ""),
            })
        if not items or not (data.get("links") or {}).get("next", True):
            break
    return out
