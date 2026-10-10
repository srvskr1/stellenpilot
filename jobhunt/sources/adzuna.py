"""Adzuna API. Bring your own free key from https://developer.adzuna.com .

Adzuna's terms allow personal research use and require crediting Adzuna wherever its data
is shown; the dashboard labels every Adzuna job with a linked "Adzuna" tag.
Default limits are 250 calls a day, so this module makes only a few calls per run.
Adzuna returns a short snippet, not the full ad text.
"""
from __future__ import annotations

from ..http import request_json
from ..text import strip_html

NAME = "adzuna"
LABEL = "Adzuna"
NEEDS = ("ADZUNA_APP_ID", "ADZUNA_APP_KEY")


def fetch(settings) -> list[dict]:
    from . import job_type_from_title

    app_id, app_key = settings.secret("ADZUNA_APP_ID"), settings.secret("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        raise RuntimeError("Adzuna is enabled but ADZUNA_APP_ID or ADZUNA_APP_KEY is missing")
    s = settings["search"]
    country = s["country"].lower()
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    base = {"app_id": app_id, "app_key": app_key, "max_days_old": s["max_age_days"],
            "results_per_page": 20, "sort_by": "date"}
    queries = [{"what": kw, "where": s["city"], "distance": s["radius_km"]} for kw in s["keywords"]]
    if s.get("include_remote"):
        queries += [{"what": kw, "what_and": "remote"} for kw in s["keywords"]]
    budget = int(settings["sources"]["limits"].get("adzuna_calls", 4))
    seen, out = set(), []
    for q in queries[:budget]:
        for r in request_json(url, params={**base, **q}).get("results", []):
            rid = str(r.get("id"))
            if rid in seen:
                continue
            seen.add(rid)
            title = strip_html(r.get("title"))
            desc = strip_html(r.get("description"))
            remote = "remote" in (title + " " + desc).lower() or "what_and" in q
            ctime = r.get("contract_time") or ""
            out.append({
                "id": f"az-{rid}",
                "source": LABEL,
                "title": title,
                "company": (r.get("company") or {}).get("display_name") or "",
                "location": ("Remote, " if remote else "") + ((r.get("location") or {}).get("display_name") or ""),
                "remote": remote,
                "url": r.get("redirect_url") or "",
                "description": desc,
                "posted_at": (r.get("created") or "")[:10],
                "job_type": job_type_from_title(title, {"full_time": "Full time", "part_time": "Part time"}.get(ctime, "")),
            })
    return out
