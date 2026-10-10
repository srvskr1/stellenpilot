"""Score jobs against the profile: an LLM when configured, keyword overlap otherwise."""
from __future__ import annotations

import re

from .text import ad_language, german_too_high, required_german_level

# Tools and skills commonly named in data job ads. Used for keyword scoring and gap tags.
VOCAB = [
    "Python", "SQL", "PySpark", "Spark", "Scala", "Java", "dbt", "Airflow", "Dagster", "Prefect",
    "Kafka", "Flink", "Snowflake", "BigQuery", "Redshift", "Databricks", "Delta Lake", "Iceberg",
    "AWS", "Azure", "GCP", "S3", "Glue", "Athena", "Lambda", "Azure Data Factory", "Synapse", "Fabric",
    "Docker", "Kubernetes", "Terraform", "Git", "CI/CD", "Linux", "Pandas", "NumPy", "scikit-learn",
    "TensorFlow", "PyTorch", "Power BI", "Tableau", "Looker", "Excel", "SAP", "PostgreSQL", "MySQL",
    "MongoDB", "NoSQL", "ETL", "ELT", "Data Modeling", "Machine Learning", "Statistics", "A/B Testing",
]
# Tool names that are also ordinary words ("I excel at", "spark interest") match case sensitively.
CASE_SENSITIVE = {"Excel", "Glue", "Fabric", "Spark", "Lambda", "Git", "Looker", "Statistics", "Athena", "Prefect", "Iceberg", "Flink"}
RE_CACHE = {v: re.compile(rf"(?<![\w/]){re.escape(v)}(?![\w/])", 0 if v in CASE_SENSITIVE else re.I) for v in VOCAB}


def is_learning_group(name: str) -> bool:
    """Skill groups named like 'Learning' hold skills you are learning, not experience."""
    return "learn" in name.lower()


def learning_items(profile: dict) -> list[str]:
    return [i for g, items in (profile.get("skills") or {}).items() if is_learning_group(g) for i in items]


def profile_text(profile: dict, include_learning: bool = True) -> str:
    """The profile as plain text. With include_learning=False it holds only real experience,
    which is what the truth guard and keyword scoring compare against."""
    p = profile.get("person") or {}
    summary = profile.get("summary") or p.get("summary") or ""
    lines = [f"Name: {p.get('name', '')}", f"Location: {p.get('location', '')}",
             f"Languages: {', '.join(p.get('languages') or [])}", f"Summary: {summary}"]
    for group, items in (profile.get("skills") or {}).items():
        if is_learning_group(group):
            if include_learning:
                lines.append(f"Currently learning, no work experience yet: {', '.join(items)}")
        else:
            lines.append(f"Skills, {group}: {', '.join(items)}")
    for e in (profile.get("experience") or []):
        lines.append(f"Experience: {e.get('title')} at {e.get('company')} ({e.get('dates')}): " + " ".join(e.get("bullets") or []))
    for pr in (profile.get("projects") or []):
        lines.append(f"Project: {pr.get('name')}: " + " ".join(pr.get("bullets") or []))
    for ed in (profile.get("education") or []):
        lines.append(f"Education: {ed.get('degree')}, {ed.get('school')} ({ed.get('dates')})")
    return "\n".join(lines)


def _mentioned(text: str) -> set[str]:
    return {v for v, rx in RE_CACHE.items() if rx.search(text or "")}


def keyword_score(job: dict, profile: dict) -> dict:
    """No-LLM fallback: share of tools named in the ad that the profile also has."""
    have = _mentioned(profile_text(profile, include_learning=False))
    want = _mentioned(job["title"] + "\n" + job["description"])
    overlap = want & have
    missing = sorted(want - have)
    # Ads that name few tools give weak evidence, so divide by at least 3.
    base = 35 + int(45 * len(overlap) / max(len(want), 3))
    title = job["title"].lower()
    if any(w in title for w in ("werkstudent", "working student", "junior", "student")):
        base += 10
    if any(w in title for w in ("senior", "lead", "principal")):
        base -= 25
    match = max(0, min(100, base))
    return {
        "match": match,
        "fit": "Strong" if match >= 75 else "Possible" if match >= 55 else "Stretch",
        "why": f"Keyword match: {', '.join(sorted(overlap)) or 'few tools named'}.",
        "gaps": ", ".join(missing[:5]) or "",
        "gap_tags": missing[:4],
    }


SYSTEM = """You score job ads for one candidate. Be honest and specific. Never assume skills the candidate does not list.
Read the candidate's skills carefully: a tool listed under Skills or used in Experience or Projects is something they HAVE.
"Currently learning" items are not experience yet. Languages show their level (A1 to C2); A2 German is NOT fluent.
Use the whole scale: 85 to 100 only when almost every requirement is met, 60 to 84 for a good fit with gaps, 40 to 59 for a stretch, below 40 for a poor fit. Most jobs land between 45 and 75.
Return JSON with keys:
match: integer 0 to 100 (skill overlap, seniority fit, location fit, language fit),
fit: "Strong", "Possible" or "Stretch",
why: one sentence on why it fits, starting with "Remote." if the job is remote,
gaps: one honest sentence on what is missing,
gap_tags: up to 4 concrete tool or skill names the ad asks for and the candidate lacks, e.g. ["dbt", "German"]. Never vague words like "cloud" or "tools".
german_fluency_required: true if the ad requires fluent, very good, C1 or native German,
summary_en: if the ad is written in German, 3 short English sentences on what the job is and what it asks for; otherwise ""."""


def llm_score(llm, job: dict, profile: dict, taste: str = "") -> dict:
    user = (f"CANDIDATE\n{profile_text(profile)}\n\n"
            + (f"CANDIDATE TASTE (from their thumbs up and down)\n{taste}\nAdjust match by at most 10 points toward this taste.\n\n" if taste else "")
            + f"JOB\nTitle: {job['title']}\nCompany: {job['company']}\nLocation: {job['location']}\n"
            f"Description:\n{job['description'][:llm.max_chars]}")
    out = llm.complete_json(SYSTEM, user, max_tokens=600)
    try:
        match = int(out.get("match") or 0)
    except (TypeError, ValueError):
        match = 0
    return {
        "match": max(0, min(100, match)),
        "fit": str(out.get("fit", "")),
        "why": str(out.get("why", "")),
        "gaps": str(out.get("gaps", "")),
        "gap_tags": ([out["gap_tags"]] if isinstance(out.get("gap_tags"), str) else [str(t) for t in (out.get("gap_tags") or [])])[:4],
        "_german": bool(out.get("german_fluency_required")),
        "summary_en": str(out.get("summary_en") or "")[:800],
    }


def taste_summary(rated: list[dict]) -> str:
    """Plain list of liked and disliked jobs. The LLM reads patterns from it."""
    likes = [f"{j['title']} at {j['company']} ({j['location']})" for j in rated if j.get("rating") == 1]
    dislikes = [f"{j['title']} at {j['company']} ({j['location']})" for j in rated if j.get("rating") == -1]
    parts = []
    if likes:
        parts.append("Liked: " + "; ".join(likes[:15]))
    if dislikes:
        parts.append("Not for me: " + "; ".join(dislikes[:15]))
    return "\n".join(parts)


SUMMARY_SYSTEM = """Summarize this German job ad in English for someone who does not read German well.
Exactly 3 short sentences: what the job is, the main tasks, and the main requirements (including the German level if stated).
Only use facts from the ad. Plain text, no lists."""


def english_summary(llm, job: dict) -> str:
    """A separate small request: small local models often skip optional fields in a bigger JSON answer."""
    try:
        text = llm.complete(SUMMARY_SYSTEM, f"{job['title']} at {job['company']}\n{job['description'][:llm.max_chars]}", max_tokens=250)
    except Exception:
        return ""
    return " ".join(text.split())[:800]


def score_job(job: dict, profile: dict, llm=None, taste: str = "", skip_german: bool = True,
              my_german: str = "A2", tolerance: int = 1) -> dict:
    text = job["title"] + "\n" + job["description"]
    level = required_german_level(text)
    if llm and llm.enabled:
        try:
            result = llm_score(llm, job, profile, taste)
        except Exception as e:  # a local model can time out or return broken JSON
            result = keyword_score(job, profile)
            result["why"] = f"{result['why']} (AI scoring failed: {str(e)[:80]}; keyword score used)"
    else:
        result = keyword_score(job, profile)
    if not level and result.pop("_german", False):
        level = "B2"  # the model saw a fluency requirement the phrase rules missed
    result.pop("_german", None)
    too_high = german_too_high(level, my_german, tolerance)
    result["german_level"] = level or ""
    result["lang"] = "German needed" if too_high else ("English" if ad_language(text) == "en" else "German ad")
    if too_high:
        if "German" not in result["gap_tags"]:
            result["gap_tags"] = ["German", *result["gap_tags"]][:4]
        if skip_german:
            result["status"] = "skipped"
            result["status_note"] = f"Ad asks for German {level}, your level is {my_german.upper()}"
    if result["lang"] != "German ad":
        result["summary_en"] = ""  # the label says "English summary of this German ad"
    elif (llm and llm.enabled and not result.get("summary_en")
            and result.get("status") != "skipped"):
        result["summary_en"] = english_summary(llm, job)
    return result
