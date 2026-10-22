"""Small text helpers: strip HTML, detect ad language and German requirements, dedupe keys."""
from __future__ import annotations

import html
import re
from functools import lru_cache

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
    s = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", s)
    s = html.unescape(_TAG.sub(" ", s)).replace("\xa0", " ")
    lines = [_WS.sub(" ", ln).strip() for ln in s.splitlines()]
    return "\n".join(ln for ln in lines if ln)


LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
# The German LANGUAGE, not the adjective: "Deutschkenntnisse", "Deutsch-", "Deutsch" as a noun,
# "German" unless it describes a company, market, speakers and so on.
_DE = re.compile(r"(?i:\bdeutsch(?:kenntniss\w*|sprach\w*|e sprache|-)|\bdeutsche\w*\s+sprach\w*)|\bDeutsch\b|\bdeutsch\b(?=\s*(?:und|sowie|oder|&|\(|:|[ABC][12]))"
                 r"|(?i:\bgerman\b(?![- ]speaking)(?!\s+(?:company|market|customers?|clients?|office|subsidiary|team|startup|branch|university|universities|speaking countries)))")
_EN = re.compile(r"(?i)\b(?:englisch\w*|english)\b")
# Describing word to CEFR level. Conventions from German career sites (see docs/sources.md), not an official standard.
_QUALIFIERS = [
    ("C2", r"muttersprach\w*|native"),
    ("C1", r"verhandlungssicher\w*|business[ -]fluent|sehr gute?\w*|exzellent\w*|excellent|very good|hervorragend\w*"),
    ("B2", r"fließend\w*|fliessend\w*|fluent(ly)?|(?<!sehr )gute?\w*|(?<!very )good|solide\w*|solid|sichere\w*|confident"),
    ("A2", r"grundkenntnisse|grundlegende\w*|basic|basis\w*"),
]
_Q = [(lvl, re.compile(rf"(?i)\b(?:{rx})")) for lvl, rx in _QUALIFIERS]
_OPTIONAL = re.compile(r"(?i)von vorteil|wünschenswert|wuenschenswert|is a plus|\ba plus\b|nice to have|ideally|optional|\bbonus\b"
                       r"|an advantage|advantageous|an asset|pluspunkt|\bpreferred\b|wäre schön|waere schoen")
_CEFR = re.compile(r"\b([ABC][12])\b")
# Abbreviations whose dot must not end a sentence ("Deutschkenntnisse (mind. B2)").
_ABBR = re.compile(r"(?i)\b(mind|min|ca|bzw|ggf|inkl|evtl|bspw|sog|z\. ?b|u\. ?a|d\. ?h)\.")
_WINDOW = 45


def _dist(m_start: int, m_end: int, spans: list[tuple[int, int]]) -> int | None:
    ds = [gs - m_end if m_end <= gs else m_start - ge if m_start >= ge else 0 for gs, ge in spans]
    return min(ds) if ds else None


_JOINED = re.compile(r"(?i)^[\s-]*(?:kenntnisse\s*)?(?:and|und|sowie|&|as well as)\s*(?:in\s+)?$")


def _coordinated(sentence: str, de: list, en: list) -> bool:
    """'English and German', 'Deutsch- und Englischkenntnisse': one describing word covers both."""
    for ds, dend in de:
        for es, eend in en:
            between = sentence[eend:ds] if eend <= ds else sentence[dend:es] if dend <= es else ""
            if between and _JOINED.match(between):
                return True
    return False


def _lang_matches(sentence: str, rx, de: list, en: list, window: int = _WINDOW) -> list[tuple[int, str]]:
    """Matches of rx that belong to a German mention: within the window, and not closer to an English
    mention, unless the two languages are joined by 'and' and so share the word."""
    joined = _coordinated(sentence, de, en)
    out = []
    for m in rx.finditer(sentence):
        d_de, d_en = _dist(m.start(), m.end(), de), _dist(m.start(), m.end(), en)
        if d_de is not None and d_de <= window and (d_en is None or d_de <= d_en or joined):
            out.append((d_de, m.group(0)))
    return out


def _level_for(text: str, main, other) -> str | None:
    """The German level an ad requires, as A1 to C2, or None if German is optional or not mentioned.
    Each sentence is read on its own, and each describing word is paired with the language it sits
    next to, so 'fluent English and basic German' means A2 and 'Deutsch C1, Englisch von Vorteil' means C1."""
    best = None
    text = _ABBR.sub(lambda m: m.group(1).replace(".", ""), text or "")
    for sentence in re.split(r"(?<=[.!?\n•;])", text):
        de = [(m.start(), m.end()) for m in main.finditer(sentence)]
        if not de:
            continue
        en = [(m.start(), m.end()) for m in other.finditer(sentence)]
        codes = [c.upper() for _, c in _lang_matches(sentence, _CEFR, de, en, window=30)]
        found = max(codes, key=LEVELS.index) if codes else None
        if not found:
            hits = [(min(d for d, _ in ms), lvl) for lvl, rx in _Q if (ms := _lang_matches(sentence, rx, de, en))]
            found = min(hits)[1] if hits else None
        if found and _lang_matches(sentence, _OPTIONAL, de, en):
            continue  # "Deutschkenntnisse von Vorteil": nice to have, not required
        if found and (best is None or LEVELS.index(found) > LEVELS.index(best)):
            best = found
    return best


def required_german_level(text: str) -> str | None:
    """The German level an ad requires (or a text claims), A1 to C2, or None."""
    return _level_for(text, _DE, _EN)


def claimed_english_level(text: str) -> str | None:
    """The English level a text claims, A1 to C2, or None."""
    return _level_for(text, _EN, _DE)


def profile_language_level(profile: dict, language: str) -> str | None:
    """Level of 'german' or 'english' from the profile's languages list, e.g. 'German (A2)'."""
    names = {"german": r"german|deutsch", "english": r"english|englisch"}[language]
    for entry in (profile.get("person") or {}).get("languages") or []:
        if re.search(rf"(?i)\b(?:{names})", str(entry)):
            return normalize_level(re.sub(rf"(?i)\b(?:{names})\w*", "", str(entry)))
    return None


_LEVEL_WORDS = {"native": "C2", "muttersprache": "C2", "muttersprachlich": "C2", "mother tongue": "C2",
                "fluent": "B2", "fließend": "B2", "fliessend": "B2", "basic": "A2", "grundkenntnisse": "A2"}


def normalize_level(value) -> str | None:
    """'B2+', 'b2', 'native', 'Muttersprache', 'B2/C1' -> a CEFR level (the lower one for ranges), else None."""
    v = str(value or "").strip().lower()
    if not v:
        return None
    m = re.search(r"\b([abc][12])", v)
    if m:
        return m.group(1).upper()
    for word, lvl in _LEVEL_WORDS.items():
        if word in v:
            return lvl
    return None


def german_too_high(required: str | None, mine: str, tolerance: int = 1) -> bool:
    """True when the ad asks for more than your level plus `tolerance` steps (A2 + 1 allows B1)."""
    req, have = normalize_level(required), normalize_level(mine) or "A2"
    if not req:
        return False
    return LEVELS.index(req) > LEVELS.index(have) + tolerance


def requires_fluent_german(text: str) -> bool:
    """Kept for compatibility: True when the ad needs B2 or higher."""
    lvl = required_german_level(text)
    return bool(lvl) and LEVELS.index(lvl) >= LEVELS.index("B2")


@lru_cache(maxsize=4096)  # /api/state checks every ad on each refresh
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
