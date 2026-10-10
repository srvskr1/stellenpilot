"""TheirStack job search API. Bring your own key from https://theirstack.com .

The free plan has 200 API credits a month and every returned job costs 1 credit,
so this module asks for a small, fixed number of jobs per run (sources.limits.theirstack_jobs).
Their terms forbid sharing keys: every user needs their own.
"""
from __future__ import annotations

import re

from ..http import request_json
from ..text import strip_html

NAME = "theirstack"
LABEL = "TheirStack"
NEEDS = ("THEIRSTACK_API_KEY",)
URL = "https://api.theirstack.com/v1/jobs/search"


def _title_patterns(keywords: list[str]) -> list[str]:
    # "Werkstudent Data" -> "werkstudent.*data", order free via two patterns
    pats = []
    for kw in keywords:
        words = [re.escape(w.lower()) for w in kw.split()]
        pats.append(".*".join(words))
        if len(words) == 2:
            pats.append(".*".join(reversed(words)))
    return pats


def fetch(settings) -> list[dict]:
    from . import job_type_from_title

    key = settings.secret("THEIRSTACK_API_KEY")
    if not key:
        raise RuntimeError("TheirStack is enabled but THEIRSTACK_API_KEY is missing")
    s = settings["search"]
    ts_cfg = settings["sources"].get("theirstack_options", {})
    budget = int(settings["sources"]["limits"].get("theirstack_jobs", 6))
    common = {
        "posted_at_max_age_days": int(s["max_age_days"]),
        "job_country_code_or": [s["country"].upper()],
        "job_title_pattern_or": _title_patterns(s["keywords"]),
        "company_type": "direct_employer",
    }
    if ts_cfg.get("english_only", True):
        common["job_description_pattern_and"] = [r"(?i)\b(you will|your tasks|what you|we are looking|you have|requirements|responsibilities)\b"]
    queries = []
    remote_n = min(2, budget // 3) if s.get("include_remote") else 0
    local = {"limit": budget - remote_n}
    if ts_cfg.get("location_ids"):
        local["job_location_or"] = [{"id": int(i)} for i in ts_cfg["location_ids"]]
    queries.append(local)
    if remote_n:
        queries.append({"limit": remote_n, "workplace_types_or": ["remote"]})
    out = []
    for q in queries:
        data = request_json(URL, body={**common, **q}, method="POST",
                            headers={"Authorization": f"Bearer {key}"})
        for j in data.get("data", []):
            title = j.get("job_title", "")
            remote = bool(j.get("remote"))
            out.append({
                "id": f"ts-{j['id']}",
                "source": LABEL,
                "title": title,
                "company": j.get("company") or (j.get("company_object") or {}).get("name", ""),
                "location": ("Remote, " if remote else "") + (j.get("short_location") or j.get("location") or ""),
                "remote": remote,
                "url": j.get("final_url") or j.get("url") or "",
                "description": strip_html(j.get("description")),
                "posted_at": (j.get("date_posted") or "")[:10],
                "job_type": job_type_from_title(title, "Part time" if "part_time" in (j.get("employment_statuses") or []) else ""),
            })
    return out
