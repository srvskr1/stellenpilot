"""Pay and deadlines read from the ad text, and the EU Blue Card salary line.

No source sends a salary field, so the yearly pay is read from the words around a euro amount.
Only amounts next to a pay word count (Gehalt, salary, brutto ...), so a training budget or a
bonus is not taken for the salary. Hourly pay is ignored. Everything is local, nothing is sent.
"""
from __future__ import annotations

import re
import statistics
from datetime import date
from functools import lru_cache

# Both Blue Card lines are fixed shares of the yearly pension contribution ceiling (Beitragsbemessungsgrenze
# Rentenversicherung): 50% for all jobs, 45.3% for shortage jobs (IT, STEM, health), new graduates and IT staff
# without a degree. Add each new year's ceiling once the Bundesrat approves it (usually late November).
# 2027: cabinet set 106,200 on 7 Oct 2026, Bundesrat still pending, so not added yet.
PENSION_CEILING = {2025: 96600, 2026: 101400}


def blue_card_lines(year: int) -> dict:
    """The lines for a year, from the newest known ceiling at or before it."""
    y = max((k for k in PENSION_CEILING if k <= year), default=min(PENSION_CEILING))
    c = PENSION_CEILING[y]
    return {"year": y, "regular": round(c * 0.5, 2), "shortage": round(c * 0.453, 2)}


# The dashboard shows the source and the date, and warns once the year has passed.
BLUE_CARD = {
    **blue_card_lines(max(PENSION_CEILING)),
    "source": "Bundesagentur für Arbeit, International Services Spotlight, issue 03/2026 (section 18g AufenthG)",
    "url": "https://www.arbeitsagentur.de/vor-ort/zav/working-and-living-in-germany/iss-en/issue-03-2026/blue-card",
    "checked": "2026-10-24",
}
MIN_PEERS = 5

_CUR = r"(?:€|EUR\b|Euro\b)"
_AMT = r"\d{1,3}(?:[.,  ]\d{3})+(?:,\d{2})?|\d{2,3}(?:[.,]\d)?\s?[kK]\b|\d{4,6}"
_DASH = r"\s*(?:-|–|—|bis|to)\s*"
_ONE = rf"(?:{_CUR}\s?)?({_AMT})(?:\s?{_CUR})?"
_RANGE = re.compile(rf"{_ONE}(?:{_DASH}{_ONE})?", re.I)
_PAYWORD = re.compile(r"gehalt|vergütung|verguetung|salary|compensation|brutto|gross|bezahlung|entgelt|"
                      r"p\.\s?a\.|per annum|pro jahr|jährlich|annual|a year|/year|/jahr|pay range|base pay", re.I)
_NOT_PAY = re.compile(r"budget|bonus|prämie|praemie|zuschuss|umsatz|revenue|funding|kunden|mitarbeiter|employees|"
                      r"weiterbildung|training|relocation|umzug", re.I)
_MONTH = re.compile(r"monat|month|mtl\.|/m\b|p\.\s?m\.", re.I)
# "bis zu 60k" / "up to €60k" is a ceiling, not the pay: the real offer can be far lower, which would
# give a false yes on the Blue Card check. Such ads count as naming no pay.
_CEILING = re.compile(r"(?:bis zu|up to|maximal|max\.|maximum|höchstens|hoechstens)\s*$", re.I)
_HOUR = re.compile(r"stunde|hour|/h\b|std\.", re.I)


def _num(s: str) -> float:
    s = s.replace(" ", " ").strip()
    if s[-1] in "kK":
        return float(s[:-1].strip().replace(",", ".")) * 1000
    s = re.sub(r",\d{2}$", "", s)  # 45.934,20 -> 45.934
    return float(re.sub(r"[.,\s]", "", s))


@lru_cache(maxsize=4096)
def salary(text: str) -> tuple[int, int] | None:
    """Yearly gross pay in euro as (low, high), or None when the ad states none."""
    for m in _RANGE.finditer(text or ""):
        whole = m.group(0)
        if not re.search(_CUR, whole, re.I) and not re.search(r"\d\s?[kK]\b", whole):
            continue
        before, after = text[max(0, m.start() - 80):m.start()], text[m.end():m.end() + 40]
        if not _PAYWORD.search(before + whole + after) or _NOT_PAY.search(before[-40:]):
            continue
        if _HOUR.search(after[:15]):
            continue
        if not m.group(2) and _CEILING.search(before[-20:]):
            return None
        lo = _num(m.group(1))
        hi = _num(m.group(2)) if m.group(2) else lo
        if _MONTH.search(after[:20]) or (lo < 12000 and _MONTH.search(before[-30:])):
            lo, hi = lo * 12, hi * 12
        lo, hi = min(lo, hi), max(lo, hi)
        if 12000 <= lo <= 300000 and hi <= 400000:
            return int(lo), int(hi)
    return None


_MONTHS = {m: i + 1 for i, names in enumerate([
    "januar january jan", "februar february feb", "märz maerz march mar", "april apr", "mai may",
    "juni june jun", "juli july jul", "august aug", "september sep sept", "oktober october okt oct",
    "november nov", "dezember december dez dec"]) for m in names.split()}
_DEADLINE = re.compile(r"(?:bewerbungsfrist|bewerbungsschluss|bewerbungen? bis|bis zum|bis spätestens|spätestens bis|"
                       r"apply by|apply before|application deadline|deadline|closing date)\D{0,15}?"
                       r"(\d{1,2})\.?\s?(?:(\d{1,2})\.|([a-zäA-Z]+)\.?)\s?(\d{4}|\d{2})?", re.I)


@lru_cache(maxsize=4096)
def deadline(text: str, found: str = "") -> str:
    """The application deadline the ad states, as YYYY-MM-DD, or "" when it states none."""
    try:
        seen = date.fromisoformat((found or "")[:10])
    except ValueError:
        seen = date.today()
    for m in _DEADLINE.finditer(text or ""):
        day, mon_num, mon_name, year = m.groups()
        mon = int(mon_num) if mon_num else _MONTHS.get((mon_name or "").lower())
        if not mon:
            continue
        y = int(year) + (2000 if year and len(year) == 2 else 0) if year else seen.year
        try:
            d = date(y, mon, int(day))
            if not year and d < seen:
                d = date(y + 1, mon, int(day))
        except ValueError:
            continue
        if 0 <= (d - seen).days <= 180:
            return d.isoformat()
    return ""


def blue_card(low: int, today: date | None = None) -> dict:
    """Is this pay enough for an EU Blue Card? "yes", "shortage" (only some jobs, with approval) or "no"."""
    today = today or date.today()
    verdict = "yes" if low >= BLUE_CARD["regular"] else "shortage" if low >= BLUE_CARD["shortage"] else "no"
    return {"verdict": verdict, "stale": today.year > BLUE_CARD["year"]}


def _city(job: dict) -> str:
    return re.split(r"[,(/]", job.get("location") or "")[0].strip().lower()


def fill_pay(jobs: list[dict]) -> None:
    """Pay, deadline and how the pay compares with the other jobs this person found."""
    for j in jobs:
        p = salary(j.get("title", "") + "\n" + (j.get("description") or ""))
        j["pay"] = {"lo": p[0], "hi": p[1]} if p else None
        j["deadline"] = deadline(j.get("description") or "", j.get("found_at") or j.get("foundAt") or "")
    paid = [j for j in jobs if j["pay"]]
    mid = lambda j: (j["pay"]["lo"] + j["pay"]["hi"]) / 2
    by_city: dict[str, list[float]] = {}
    for j in paid:
        by_city.setdefault(_city(j), []).append(mid(j))
    overall = statistics.median(map(mid, paid)) if len(paid) >= MIN_PEERS else None
    for j in paid:
        near = by_city.get(_city(j), [])
        med, peers, where = ((statistics.median(near), len(near), (j.get("location") or "").split(",")[0].strip())
                             if len(near) >= MIN_PEERS and _city(j) else (overall, len(paid), ""))
        j["pay"].update(peers=peers, near=where, median=int(med) if med else None,
                        fair=None if not med else "below" if mid(j) < med * 0.9 else "above" if mid(j) > med * 1.1 else "average",
                        **blue_card(j["pay"]["lo"]))
    if overall:  # for ads without pay: "similar jobs you found pay about ..."
        for j in jobs:
            if not j["pay"]:
                j["payHint"] = {"median": int(overall), "peers": len(paid)}
