"""Bundesagentur fuer Arbeit job search (Germany).

Public endpoint used by the BA's own job search, documented by the community at
https://jobsuche.api.bund.dev/ . The client id below is the public one from that documentation.
No official terms or rate limits are published, so this module keeps requests few and small.
"""
from __future__ import annotations

import base64

from ..http import HttpError, request_json
from ..text import strip_html, title_excluded

NAME = "arbeitsagentur"
LABEL = "Bundesagentur für Arbeit"
BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}


def _search(params: dict) -> list[dict]:
    data = request_json(f"{BASE}/pc/v6/jobs", params=params, headers=HEADERS)
    return data.get("ergebnisliste") or []


def _details(refnr: str) -> dict:
    enc = base64.b64encode(refnr.encode()).decode()
    try:
        return request_json(f"{BASE}/pc/v4/jobdetails/{enc}", headers=HEADERS)
    except HttpError:
        return {}


def _normalize(item: dict, detail: dict) -> dict:
    from . import job_type_from_title

    loc = (item.get("stellenlokationen") or [{}])[0].get("adresse", {})
    ref = item["referenznummer"]
    title = item.get("stellenangebotsTitel") or item.get("titel") or ""
    remote = bool(item.get("homeofficemoeglich")) and (item.get("homeofficeprozent") or 0) >= 80
    return {
        "id": f"ba-{ref}",
        "source": LABEL,
        "title": title,
        "company": item.get("firma") or item.get("arbeitgeber") or "",
        "location": ("Remote, " if remote else "") + ", ".join(x for x in (loc.get("ort"), loc.get("region", "").replace("_", " ").title()) if x),
        "remote": remote,
        "url": detail.get("externeUrl") or f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}",
        "description": strip_html(detail.get("stellenangebotsBeschreibung", "")),
        "posted_at": item.get("datumErsteVeroeffentlichung") or "",
        "job_type": job_type_from_title(title),
    }


def fetch(settings) -> list[dict]:
    s = settings["search"]
    size = int(settings["sources"]["limits"].get("arbeitsagentur_results", 50))
    seen, out = set(), []
    queries = [{"wo": s["city"], "umkreis": s["radius_km"]}]
    if s.get("include_remote"):
        queries.append({"arbeitszeit": "ho"})  # home office / telework, whole country
    for kw in s["keywords"]:
        for q in queries:
            params = {"was": kw, "angebotsart": 1, "veroeffentlichtseit": s["max_age_days"],
                      "size": min(size, 100), "page": 1, **q}
            for item in _search(params):
                ref = item.get("referenznummer")
                title = item.get("stellenangebotsTitel") or ""
                if not ref or ref in seen or title_excluded(title, s.get("exclude_title_words", [])):
                    continue
                seen.add(ref)
                out.append(_normalize(item, _details(ref)))
                if len(out) >= size:
                    return out
    return out
