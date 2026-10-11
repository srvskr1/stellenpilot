"""Adzuna API. Bring your own free key from https://developer.adzuna.com .

Adzuna's terms allow personal research use and require crediting Adzuna wherever its data
is shown; the dashboard labels every Adzuna job with a linked "Adzuna" tag.
Default limits are 250 calls a day (and 2500 a month), so each run stays inside a call budget
(sources.limits.adzuna_calls, default 20): every query gets page 1 first, then further pages
while budget is left and the previous page was full.
Adzuna returns a short snippet, not the full ad text.
"""
from __future__ import annotations

from ..http import request_json
from ..text import strip_html

NAME = "adzuna"
# Countries the Adzuna API serves (from its OpenAPI spec).
COUNTRIES = {"gb", "us", "at", "au", "be", "br", "ca", "ch", "de", "es", "fr", "in", "it", "mx", "nl", "nz", "pl", "sg", "za"}
LABEL = "Adzuna"
NEEDS = ("ADZUNA_APP_ID", "ADZUNA_APP_KEY")
PER_PAGE = 50  # the most Adzuna returns per call


def _normalize(r: dict, q: dict, job_type_from_title) -> dict:
    rid = str(r.get("id"))
    title = strip_html(r.get("title"))
    desc = strip_html(r.get("description"))
    remote = "remote" in (title + " " + desc).lower() or "what_and" in q
    ctime = r.get("contract_time") or ""
    return {
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
    }


def fetch(settings) -> list[dict]:
    from . import job_type_from_title

    app_id, app_key = settings.secret("ADZUNA_APP_ID"), settings.secret("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        raise RuntimeError("Adzuna is enabled but ADZUNA_APP_ID or ADZUNA_APP_KEY is missing")
    s = settings["search"]
    country = s["country"].lower()
    base = {"app_id": app_id, "app_key": app_key, "max_days_old": s["max_age_days"],
            "results_per_page": PER_PAGE, "sort_by": "date"}
    queries = [{"what": kw, "where": s["city"], "distance": s["radius_km"]} for kw in s["keywords"]]
    if s.get("include_remote"):
        queries += [{"what": kw, "what_and": "remote"} for kw in s["keywords"]]
    limits = settings["sources"]["limits"]
    budget = int(limits.get("adzuna_calls", 20))
    max_pages = int(limits.get("adzuna_pages", 5))
    seen, out = set(), []
    # Breadth first: page 1 of every query, then page 2 of those that had more, and so on.
    open_queries = list(queries)
    for page in range(1, max_pages + 1):
        still_open = []
        for q in open_queries:
            if budget <= 0:
                return out
            budget -= 1
            results = request_json(f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}",
                                   params={**base, **q}).get("results", [])
            for r in results:
                job = _normalize(r, q, job_type_from_title)
                if job["id"] not in seen:
                    seen.add(job["id"])
                    out.append(job)
            if len(results) >= PER_PAGE:
                still_open.append(q)
        open_queries = still_open
        if not open_queries:
            break
    return out
