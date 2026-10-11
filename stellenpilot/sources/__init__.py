"""Job sources. Each module exposes NAME and fetch(settings) -> list[dict] of normalized jobs.

A normalized job has: id, source, title, company, location, remote, url, description,
posted_at (YYYY-MM-DD or ''), job_type ('Werkstudent', 'Full time', 'Part time' or '').
Only official or public APIs are used. No scraping of sites whose terms forbid it.
"""
from __future__ import annotations

from . import adzuna, arbeitnow, arbeitsagentur, jobicy, remotive, theirstack, watchlist

REGISTRY = {m.NAME: m for m in (watchlist, arbeitsagentur, arbeitnow, adzuna, theirstack, jobicy, remotive)}


def title_has_keyword(title: str, keywords: list[str]) -> bool:
    """True when every word of at least one keyword is in the title ("Werkstudent Data")."""
    t = (title or "").lower()
    return any(all(w in t for w in kw.lower().split()) for kw in keywords)


def job_type_from_title(title: str, fallback: str = "") -> str:
    t = (title or "").lower()
    if "werkstudent" in t or "working student" in t or "studentische" in t:
        return "Werkstudent"
    if "teilzeit" in t or "part time" in t or "part-time" in t:
        return "Part time"
    return fallback
