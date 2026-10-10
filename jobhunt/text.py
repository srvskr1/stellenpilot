"""Small text helpers: strip HTML, detect ad language and German requirements, dedupe keys."""
from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")

FLUENT_GERMAN = [
    re.compile(r"(?i)(fließend|fliessend|sehr gute?n?|verhandlungssicher|exzellente?n?|fluent|excellent|very good|business fluent|C1|C2|muttersprach\w*|native)[^.\n]{0,40}(deutsch|german)"),
    re.compile(r"(?i)(deutsch|german)[^.\n]{0,30}(fließend|fliessend|verhandlungssicher|C1|C2|fluent|native|muttersprach\w*)"),
]

_EN_WORDS = re.compile(r"\b(the|and|you|your|with|our|we|will|experience|skills|team)\b", re.I)
_DE_WORDS = re.compile(r"\b(und|die|der|das|wir|sie|du|mit|für|deine|ihre|kenntnisse|erfahrung)\b", re.I)


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"(?i)<\s*(br|/p|/li|/h\d)\s*/?>", "\n", s)
    s = html.unescape(_TAG.sub(" ", s)).replace("\xa0", " ")
    lines = [_WS.sub(" ", ln).strip() for ln in s.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def requires_fluent_german(text: str) -> bool:
    return any(p.search(text or "") for p in FLUENT_GERMAN)


def ad_language(text: str) -> str:
    """'en' or 'de' by counting common words. Good enough to sort ads, not a classifier."""
    en, de = len(_EN_WORDS.findall(text or "")), len(_DE_WORDS.findall(text or ""))
    return "en" if en >= de else "de"


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\((m|w|d|f|x|div|all genders?)[/|, *]*[^)]*\)", " ", s)  # (m/w/d) and friends
    s = re.sub(r"\b(gmbh|ag|se|kg|co|mbh|inc|ltd|group|germany|deutschland)\b", " ", s)
    s = re.sub(r"[^a-z0-9äöüß]+", " ", s)
    return " ".join(s.split())


def dedupe_key(company: str, title: str) -> str:
    """Same company plus same normalized title means the same job across sources."""
    return f"{_norm(company)}|{_norm(title)}"


def title_excluded(title: str, words: list[str]) -> bool:
    t = (title or "").lower()
    return any(w.lower() in t for w in words)
