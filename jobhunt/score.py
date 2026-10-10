"""Score jobs against the profile: an LLM when configured, keyword overlap otherwise."""
from __future__ import annotations

import re

from .text import ad_language, requires_fluent_german

# Tools and skills commonly named in data job ads. Used for keyword scoring and gap tags.
VOCAB = [
    "Python", "SQL", "PySpark", "Spark", "Scala", "Java", "dbt", "Airflow", "Dagster", "Prefect",
    "Kafka", "Flink", "Snowflake", "BigQuery", "Redshift", "Databricks", "Delta Lake", "Iceberg",
    "AWS", "Azure", "GCP", "S3", "Glue", "Athena", "Lambda", "Azure Data Factory", "Synapse", "Fabric",
    "Docker", "Kubernetes", "Terraform", "Git", "CI/CD", "Linux", "Pandas", "NumPy", "scikit-learn",
    "TensorFlow", "PyTorch", "Power BI", "Tableau", "Looker", "Excel", "SAP", "PostgreSQL", "MySQL",
    "MongoDB", "NoSQL", "ETL", "ELT", "Data Modeling", "Machine Learning", "Statistics", "A/B Testing",
]
RE_CACHE = {v: re.compile(rf"(?<![\w/]){re.escape(v)}(?![\w/])", re.I) for v in VOCAB}


def profile_text(profile: dict) -> str:
    p = profile.get("person", {})
    lines = [f"Name: {p.get('name', '')}", f"Location: {p.get('location', '')}",
             f"Languages: {', '.join(p.get('languages', []))}", f"Summary: {profile.get('summary', p.get('summary', ''))}"]
    for group, items in profile.get("skills", {}).items():
        lines.append(f"Skills, {group}: {', '.join(items)}")
    for e in profile.get("experience", []):
        lines.append(f"Experience: {e.get('title')} at {e.get('company')} ({e.get('dates')}): " + " ".join(e.get("bullets", [])))
    for pr in profile.get("projects", []):
        lines.append(f"Project: {pr.get('name')}: " + " ".join(pr.get("bullets", [])))
    for ed in profile.get("education", []):
        lines.append(f"Education: {ed.get('degree')}, {ed.get('school')} ({ed.get('dates')})")
    return "\n".join(lines)


def _mentioned(text: str) -> set[str]:
    return {v for v, rx in RE_CACHE.items() if rx.search(text or "")}


def keyword_score(job: dict, profile: dict) -> dict:
    """No-LLM fallback: share of tools named in the ad that the profile also has."""
    have = _mentioned(profile_text(profile))
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
Return JSON with keys:
match: integer 0 to 100 (skill overlap, seniority fit, location fit, language fit),
fit: "Strong", "Possible" or "Stretch",
why: one sentence on why it fits, starting with "Remote." if the job is remote,
gaps: one honest sentence on what is missing,
gap_tags: up to 4 short names of missing skills or requirements, e.g. ["dbt", "German"],
german_fluency_required: true if the ad requires fluent, very good, C1 or native German."""


def llm_score(llm, job: dict, profile: dict, taste: str = "") -> dict:
    user = (f"CANDIDATE\n{profile_text(profile)}\n\n"
            + (f"CANDIDATE TASTE (from their thumbs up and down)\n{taste}\nAdjust match by at most 10 points toward this taste.\n\n" if taste else "")
            + f"JOB\nTitle: {job['title']}\nCompany: {job['company']}\nLocation: {job['location']}\n"
            f"Description:\n{job['description'][:6000]}")
    out = llm.complete_json(SYSTEM, user, max_tokens=600)
    match = int(out.get("match", 0))
    return {
        "match": max(0, min(100, match)),
        "fit": str(out.get("fit", "")),
        "why": str(out.get("why", "")),
        "gaps": str(out.get("gaps", "")),
        "gap_tags": [str(t) for t in (out.get("gap_tags") or [])][:4],
        "_german": bool(out.get("german_fluency_required")),
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


def score_job(job: dict, profile: dict, llm=None, taste: str = "", skip_german: bool = True) -> dict:
    text = job["title"] + "\n" + job["description"]
    german_req = requires_fluent_german(text)
    result = llm_score(llm, job, profile, taste) if (llm and llm.enabled) else keyword_score(job, profile)
    german_req = german_req or result.pop("_german", False)
    lang = "German needed" if german_req else ("English" if ad_language(text) == "en" else "German ad")
    result["lang"] = lang
    if german_req and skip_german:
        result["status"] = "skipped"
        result["status_note"] = "Ad asks for fluent German"
        if "German" not in result["gap_tags"]:
            result["gap_tags"] = ["German", *result["gap_tags"]][:4]
    return result
