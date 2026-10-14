"""Sort CV text into a profile without rewriting it.

Two ways to find where each part of the CV is, then one shared way to turn those lines into
profile fields:

* rules: section headings ("Experience", "Berufserfahrung"), date ranges and bullet points.
  Instant, and enough for most clean CVs.
* AI with line numbers: when the rules are unsure, the AI sees the numbered lines and answers
  only with line ranges ("job: header 19, bullets 20 to 23"). It writes about a tenth of what it
  would write if it copied the CV, so a model on a laptop needs a minute or two instead of ten.

Either way every field is copied from the CV itself, so nothing can be reworded or made up.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- lines and bullets

BULLET = re.compile(r"^\s*[•●▪‣◦○■□➢►▶✓✔\-–—*·]\s+")
_MONTH = (r"(?:jan(?:uary|uar)?|feb(?:ruary|ruar)?|m(?:ar(?:ch)?|är(?:z)?|aerz)|apr(?:il)?|ma[iy]|jun[ei]?|jul[iy]?"
          r"|aug(?:ust)?|sep(?:t(?:ember)?)?|o[ck]t(?:ober)?|nov(?:ember)?|de[cz](?:ember)?)\.?")
_POINT = rf"(?:{_MONTH}\s*\d{{4}}|\d{{1,2}}\s*[/.]\s*\d{{4}}|(?:19|20)\d{{2}})"
_NOW = r"(?:present|now|today|current|ongoing|heute|aktuell|laufend|jetzt|dato|bis\s+heute)"
DATES = re.compile(rf"(?i)(?:(?:since|seit)\s+{_POINT}|{_POINT}\s*(?:to|until|bis|[-–—])\s*(?:{_POINT}|{_NOW})|{_POINT})")
_SENT_END = re.compile(r"[.!?:)]\s*$")

HEADINGS = {
    "summary": ("summary", "profile", "about me", "about", "objective", "profil", "kurzprofil", "zusammenfassung",
                "über mich", "ueber mich"),
    "skills": ("skills", "technical skills", "kenntnisse", "fähigkeiten", "faehigkeiten", "technologies", "tech stack",
               "competencies", "kompetenzen", "it-kenntnisse", "it kenntnisse", "tools"),
    "experience": ("experience", "work experience", "professional experience", "employment", "work history",
                   "berufserfahrung", "praxiserfahrung", "beruflicher werdegang", "berufliche erfahrung", "werdegang",
                   "career"),
    "projects": ("projects", "projekte", "portfolio"),
    "education": ("education", "ausbildung", "studium", "bildung", "academic background", "schulbildung"),
    "languages": ("languages", "sprachen", "sprachkenntnisse"),
    "other": ("certification", "certifications", "certificates", "zertifikate", "awards", "interests", "hobbies",
              "volunteering", "ehrenamt", "publications", "references", "referenzen", "achievements", "courses",
              "weiterbildung", "interessen"),
}


def _clean(s: str) -> str:
    return " ".join((s or "").split())


def heading_of(line: str) -> str | None:
    """The section a heading line opens, or None. 'Data Engineering Projects' opens projects."""
    t = _clean(line).strip(":").strip()
    if not t or BULLET.match(line) or len(t.split()) > 5 or re.search(r"\d", t) or t.endswith((".", ",")) or "@" in t:
        return None
    low = t.lower()
    for section, words in HEADINGS.items():
        for w in words:
            if low == w or low.endswith(" " + w) or low.startswith(w + " ") and len(t.split()) <= 3:
                return section
    return None


def join_lines(text: str) -> list[dict]:
    """CV lines with bullets that a PDF broke over several lines joined back together.
    Each item: {"text", "bullet": bool, "lines": [original line numbers, 1 based]}."""
    out: list[dict] = []
    for no, raw in enumerate(text.splitlines(), 1):
        t = _clean(raw)
        if not t:
            continue
        if BULLET.match(raw):
            out.append({"text": _clean(BULLET.sub("", raw)), "bullet": True, "lines": [no]})
            continue
        prev = out[-1] if out else None
        continues = (prev and prev["bullet"] and heading_of(t) is None and not DATES.search(t)
                     and (not _SENT_END.search(prev["text"]) or t[:1].islower()))
        if continues:
            prev["text"] = f"{prev['text']} {t}"
            prev["lines"].append(no)
        else:
            # A full sentence under a job ("Built batch pipelines in Airflow ...") is a bullet without a sign.
            sentence = len(t.split()) >= 8 and bool(re.search(r"[.!?]$|\.\s", t)) and not DATES.search(t)
            out.append({"text": t, "bullet": sentence, "lines": [no]})
    return out


# ---------------------------------------------------------------- fields from lines

def split_dates(text: str) -> tuple[str, str]:
    """('Junior Data Analyst, Techmak Technology', 'Sep 2020 to Sep 2023') from one header line."""
    found = list(DATES.finditer(text))
    if not found:
        return text.strip(" |,–-"), ""
    m = max(found, key=lambda x: len(x.group(0)))
    rest = (text[:m.start()] + " " + text[m.end():]).strip()
    rest = re.sub(r"[\s|,–—-]+$", "", re.sub(r"^[\s|,–—-]+", "", rest))
    return _clean(re.sub(r"\(\s*\)", "", rest)), _clean(m.group(0))


_SEP = re.compile(r"\s*(?:,|\s\|\s|\s@\s|\sat\s|\sbei\s|\s[–—]\s)\s*")
_LINK = re.compile(r"(?i)\b(?:https?://\S+|(?:www\.)?(?:github\.com|gitlab\.com|linkedin\.com|kaggle\.com)/\S+)")


def _parts(text: str) -> list[str]:
    return [p for p in _SEP.split(text) if p]


def entry(items: list[dict], kind: str) -> dict:
    """One job, project or degree from its header lines and bullets."""
    heads = [i["text"] for i in items if not i["bullet"]]
    bullets = [i["text"] for i in items if i["bullet"]]
    dates, link, names = "", "", []
    for h in heads:
        m = _LINK.search(h)
        if m and not link:
            link = m.group(0).rstrip(".,)")
            h = (h[:m.start()] + h[m.end():]).strip()
        rest, d = split_dates(h)
        dates = dates or d
        if rest and not (kind == "projects" and names and _tech_line(rest)):
            names.append(rest)
    if kind == "projects":
        return {"name": names[0] if names else "", "link": link, "bullets": bullets, "dates": dates}
    head = ", ".join(names)
    parts = _parts(head)
    first, second = (parts[0] if parts else ""), ", ".join(parts[1:])
    if kind == "education":
        return {"degree": first, "school": second, "dates": dates}
    return {"title": first, "company": second, "dates": dates, "bullets": bullets}


def _tech_line(text: str) -> bool:
    """'Azure Data Factory · ADLS Gen2 · Databricks': a list of tools under a project name."""
    return text.count("·") >= 2 or text.count("|") >= 2 or (text.count(",") >= 3 and not re.search(r"\b(and|und|the|der|die)\b", text))


def split_entries(items: list[dict]) -> list[list[dict]]:
    """A new entry starts at a header line that follows bullets (or at the very first line)."""
    groups: list[list[dict]] = []
    for it in items:
        starts = not groups or (not it["bullet"] and any(x["bullet"] for x in groups[-1]))
        # A dated header line also starts a new entry when the previous one had no bullets.
        if groups and not it["bullet"] and not starts and DATES.search(it["text"]) and any(DATES.search(x["text"]) for x in groups[-1]):
            starts = True
        if starts:
            groups.append([it])
        else:
            groups[-1].append(it)
    return groups


def skills_from(items: list[dict]) -> dict[str, list[str]]:
    """'Group: a, b (c, d), e' lines; lines without a colon continue the group above."""
    groups: dict[str, str] = {}
    current = "Skills"
    for it in items:
        t = it["text"]
        m = re.match(r"^([^:,]{2,40}):\s*(.*)$", t)
        if m:
            current = _clean(m.group(1))
            groups[current] = m.group(2)
        else:
            groups[current] = (groups.get(current, "") + (", " if it["bullet"] else " ") + t).lstrip(" ,")
    out = {}
    for g, text in groups.items():
        vals, depth, buf = [], 0, ""
        for ch in text:
            depth += ch in "([" and 1 or ch in ")]" and -1 or 0
            if ch in ",;·|•" and depth == 0:
                vals.append(buf)
                buf = ""
            else:
                buf += ch
        vals.append(buf)
        # A skill is a name, not a sentence: longer pieces are text that ran into the skills by mistake.
        # Words in brackets do not count: "AWS (S3, Glue, Athena, IAM)" is one skill.
        vals = [_clean(v).strip(" .") for v in vals
                if _clean(v).strip(" .") and len(re.sub(r"\([^)]*\)", "", v).split()) <= 6]
        if vals:
            out["Learning" if "learn" in g.lower() and g != "Learning" and "machine" not in g.lower() else g] = vals
    return out


def person_from(lines: list[dict], contact: dict) -> dict:
    """Name, headline and location from the lines above the first section."""
    person = dict(contact)
    top = [i["text"] for i in lines]
    if top:
        # The name is the first line, without the e-mail, phone or links some CVs put next to it.
        first = _LINK.sub("", re.sub(r"\S+@\S+|\+?\d[\d ()/.-]{7,}\d", "", top[0]))
        first = _clean(re.sub(r"[|·•,]", " ", first))
        if first and len(first.split()) <= 4 and not re.search(r"\d", first):
            person["name"] = first
        else:
            person["name"] = person.get("name") or top[0]
    for t in top[1:4]:
        if "@" in t or re.search(r"\+?\d[\d ()/.-]{7,}", t):
            for seg in re.split(r"\s*[|·•]\s*", t):
                if (seg and "@" not in seg and not re.search(r"\d{3}", seg) and not _LINK.search(seg)
                        and "." not in seg and len(seg) < 40 and not person.get("location")):
                    person["location"] = seg.strip()
        elif "|" in t and not person.get("headlines"):
            person["headlines"] = [t]
    return person


# ---------------------------------------------------------------- the two ways to find sections

def by_rules(text: str) -> dict[str, list[dict]]:
    """Section name to its lines, by headings. Lines before the first heading are 'top'."""
    sections: dict[str, list[dict]] = {"top": []}
    current = "top"
    for it in join_lines(text):
        h = None if it["bullet"] else heading_of(it["text"])
        if h:
            current = h
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(it)
    return sections


def build(sections: dict[str, list[dict]], contact: dict, entries: dict[str, list[list[dict]]] | None = None) -> dict:
    """A profile from sorted lines. `entries` may give the job, project and degree groups directly
    (the AI does); otherwise they are split by header lines and bullets."""
    entries = entries or {}
    profile = {"person": person_from(sections.get("top", []), contact),
               "skills": skills_from(sections.get("skills", [])), "experience": [], "projects": [], "education": []}
    summary = " ".join(i["text"] for i in sections.get("summary", []))
    if summary:
        profile["person"]["summary"] = summary
    for kind in ("experience", "projects", "education"):
        groups = entries.get(kind) or split_entries(sections.get(kind, []))
        for g in groups:
            e = entry(g, kind)
            if any(v for k, v in e.items() if k in ("title", "name", "degree")):
                profile[kind].append(e)
    return profile


def good_enough(profile: dict, sections: dict[str, list[dict]], source: str) -> tuple[bool, str]:
    """Whether the rule result can be trusted without an AI. Says why not, for the notes."""
    from .importer import missing_lines
    exp, proj, edu = profile["experience"], profile["projects"], profile["education"]
    if not (exp or proj):
        return False, "no jobs or projects found by headings"
    if not edu:
        return False, "no education found by headings"
    if any(not e["title"] or not e["company"] or not e["dates"] for e in exp):
        return False, "a job without title, company or dates"
    if any(not e["degree"] or not e["school"] for e in edu):
        return False, "a degree without school"
    if exp and not all(e["bullets"] for e in exp):
        return False, "a job without bullet points"
    # Lines the profile has no place for (languages, certificates, coursework under a degree) do not count.
    no_place = " ".join(i["text"] for k in ("languages", "other") for i in sections.get(k, []))
    no_place += " " + " ".join(i["text"] for i in sections.get("education", []) if i["bullet"])
    left = [ln for ln in missing_lines(profile, source) if _clean(ln) not in _clean(no_place)]
    if len(left) > 2:
        return False, f"{len(left)} CV lines did not fit any section"
    return True, ""


# ---------------------------------------------------------------- AI with line numbers

LINES_SYSTEM = """You find where things start in a CV. You never copy or rewrite text: you answer ONLY with line numbers.
Each line of the CV starts with its number in square brackets.
Return JSON with lists of line numbers:
{"summary": [lines of the summary or profile text],
 "skills": [lines that list skills],
 "experience": [the first line of each job: the line with the job title, company or dates],
 "projects": [the first line of each project: the line with the project name],
 "education": [the first line of each degree]}
One number per job, project or degree in those three lists. Use [] when the CV has none.
Do not list section headings, bullet points, languages, certificates or hobbies.
Numbers only, never text. Example of a correct answer:
{"summary": [5, 6, 7], "skills": [10, 11, 12], "experience": [15, 21], "projects": [], "education": [27, 29]}"""


def numbered(text: str) -> str:
    return "\n".join(f"[{no}] {ln.strip()}" for no, ln in enumerate(text.splitlines(), 1) if ln.strip())


def _nums(v, n: int) -> list[int]:
    """Line numbers from the answer; small models mix numbers, strings and ranges."""
    out = []
    for x in v if isinstance(v, list) else []:
        if isinstance(x, list):
            out += _nums(x, n)
        elif isinstance(x, (int, float)) or (isinstance(x, str) and x.strip().isdigit()):
            if 1 <= int(x) <= n:
                out.append(int(x))
    return sorted(set(out))


def _looks_like_heading(text: str) -> bool:
    """'What I studied', 'Toolbox': a short line without dates or links, like a heading we do not know."""
    return len(text.split()) <= 4 and not re.search(r"\d", text) and not _LINK.search(text) and not text.endswith(".")


def _trim(group: list[dict]) -> list[dict]:
    """An entry ends with its bullets: a header-like line after them, or a short heading-like line at the
    end of an entry without bullets, belongs to the next part of the CV."""
    out = []
    for it in group:
        if not it["bullet"] and any(x["bullet"] for x in out):
            break
        out.append(it)
    while len(out) > 1 and not out[-1]["bullet"] and _looks_like_heading(out[-1]["text"]):
        out.pop()
    return out


def by_line_numbers(answer: dict, text: str) -> tuple[dict[str, list[dict]], dict[str, list[list[dict]]]]:
    """Turn the AI's start lines back into sorted lines. Each job, project or degree runs from its
    start line to the next start line or section heading; bullets are joined as for the rules."""
    joined = join_lines(text)
    raw = text.splitlines()
    n = len(raw)
    at = {no: it for it in joined for no in it["lines"]}
    answer = answer if isinstance(answer, dict) else {}
    starts = {k: _nums(answer.get(k), n) for k in ("experience", "projects", "education")}
    lists = {k: _nums(answer.get(k), n) for k in ("summary", "skills")}
    headings = {no for no, ln in enumerate(raw, 1) if ln.strip() and heading_of(ln) and not BULLET.match(ln)}
    all_starts = set(sum(starts.values(), []))
    hard = sorted(all_starts | headings)  # lines where a new part of the CV surely begins
    # Name and contact lines: everything before the first heading or job, project or degree.
    top_end = hard[0] if hard else n + 1
    for k, v in lists.items():
        v = [x for x in v if x >= top_end and x not in all_starts]
        if len(v) >= 2:  # one block: [5, 8] or [4, 5, 8] mean lines 4 to 8, up to the next heading or entry
            stop = next((b for b in hard if b > v[0]), n + 1)
            v = list(range(v[0], min(v[-1] + 1, stop)))
        lists[k] = v
    bounds = sorted(set(hard) | set(sum(lists.values(), [])))

    def items(nums) -> list[dict]:
        seen, out = set(), []
        for no in nums:
            it = at.get(no)
            if it and id(it) not in seen and no not in headings:
                seen.add(id(it))
                out.append(it)
        return out

    sections = {k: items(v) for k, v in lists.items()}
    sections["top"] = items(range(1, top_end))
    entries: dict[str, list[list[dict]]] = {}
    for kind, ss in starts.items():
        groups = []
        for st in ss:
            end = next((b for b in bounds if b > st), n + 1)
            g = _trim(items(range(st, end)))
            if g and not g[0]["bullet"]:
                groups.append(g)
        entries[kind] = groups
    return sections, entries
