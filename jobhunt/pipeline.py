"""The daily run: collect, score, tailor, sync Gmail. Writes live progress for the dashboard."""
from __future__ import annotations

import logging
import urllib.error
import urllib.request

from . import sources
from .db import DB, today
from .llm import LLM
from .http import USER_AGENT
from .score import profile_text, score_job, taste_summary
from .tailor import tailor_job, unsupported_claims
from .text import dedupe_key, title_excluded

log = logging.getLogger("jobhunt")
# Sources with full descriptions first, so duplicates keep the richer copy.
ORDER = ["arbeitsagentur", "theirstack", "arbeitnow", "adzuna"]


def collect(settings, db: DB) -> tuple[list[dict], list[str]]:
    enabled = [n for n in ORDER if settings["sources"].get(n)]
    known_ids, known_keys = db.job_ids(), db.dedupe_keys()
    excl = settings["search"].get("exclude_title_words", [])
    new, problems = [], []
    for name in enabled:
        db.stage("collect", f"Searching {sources.REGISTRY[name].LABEL}")
        try:
            found = sources.REGISTRY[name].fetch(settings)
        except Exception as e:  # one broken source must not stop the run
            problems.append(f"{name}: {e}")
            log.warning("source %s failed: %s", name, e)
            continue
        log.info("%s returned %d jobs", name, len(found))
        for job in found:
            key = dedupe_key(job["company"], job["title"])
            if job["id"] in known_ids or key in known_keys or title_excluded(job["title"], excl):
                continue
            known_ids.add(job["id"])
            known_keys.add(key)
            job["dedupe_key"] = key
            new.append(job)
    return new, problems


def check_closed(db: DB, limit: int = 15) -> int:
    """Mark jobs whose posting now returns 404 or 410. Other errors are ignored (could be temporary)."""
    closed = 0
    for job in db.jobs("status IN ('new', 'ready') AND closed = 0 AND url != ''")[:limit]:
        req = urllib.request.Request(job["url"], headers={"User-Agent": USER_AGENT})
        try:
            urllib.request.urlopen(req, timeout=15).close()
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                db.update_job(job["id"], {"closed": 1, "closed_at": today()})
                closed += 1
        except Exception:
            pass
    return closed


PREP_SYSTEM = """Write an interview prep pack for the candidate. Plain text, each heading on its own line starting with "## ", bullets starting with "- ".
Headings: "## About <company>" (2 to 4 lines, only what the ad says, no outside facts), "## What they will test", "## Likely questions" (6 to 8),
"## Your stories" (3 to 5 STAR stories built ONLY from the candidate's real experience, one bullet each), "## Your gaps and how to answer", "## Questions to ask them" (3 to 4).
Under 3500 characters. Do not use hyphens or dashes as punctuation inside sentences.
Return JSON: {"prep": "..."}"""


def make_prep(job: dict, profile: dict, llm) -> str:
    user = f"CANDIDATE\n{profile_text(profile)}\n\nJOB\n{job['title']} at {job['company']}\n{job.get('description', '')[:6000]}"
    text = str(llm.complete_json(PREP_SYSTEM, user, max_tokens=1800).get("prep") or "")
    # Stories must be true: drop story lines the truth guard rejects.
    out, in_stories, dropped = [], False, 0
    for line in text.splitlines():
        if line.startswith("## "):
            in_stories = "stor" in line.lower()
        elif in_stories and line.strip() and unsupported_claims(line, profile, job):
            dropped += 1
            continue
        out.append(line)
    if dropped:
        out.append(f"(Removed {dropped} story line(s) that mentioned things not in your experience.)")
    return "\n".join(out)[:4000]


def run(settings, *, tailor: bool = True) -> dict:
    db = DB(settings.db_path)
    profile = settings.profile
    if not profile:
        raise RuntimeError("profile.toml is missing. Run `jobhunt init` and fill it in.")
    llm = LLM(settings)
    day = today()
    db.run_update(day, notes="")
    db.stage("collect", "Starting the daily search")

    new, problems = collect(settings, db)

    db.stage("score", f"Scoring {len(new)} new jobs against your CV")
    taste = taste_summary(db.jobs("rating IS NOT NULL"))
    added = 0
    skip_de = settings["language"].get("skip_if_fluent_german_required", True)
    for job in new:
        try:
            job.update(score_job(job, profile, llm, taste, skip_de))
        except Exception as e:
            problems.append(f"scoring {job['id']}: {e}")
            continue
        if db.insert_job(job):
            added += 1
        else:
            problems.append(f"could not store {job['id']}")

    docs = 0
    if tailor:
        t = settings["tailor"]
        todo = [j for j in db.jobs("status = 'new' AND folder = '' AND closed = 0 AND match >= ?", (t["min_match"],))
                if j["lang"] != "German needed" and (j["lang"] == "English" or not t.get("only_english_ads", True))][: t["max_per_run"]]
        out_root = (settings.home / t["output_dir"]).resolve()
        for i, job in enumerate(todo, 1):
            db.stage("tailor", f"Tailoring CV {i} of {len(todo)}: {job['company']}")
            try:
                res = tailor_job(job, profile, out_root, llm, t.get("make_pdf", True))
            except Exception as e:
                problems.append(f"tailoring {job['id']}: {e}")
                continue
            db.mark_ready(job["id"], res["folder"], f"Your experience shows {res['coverage']}% of the tools the ad names")
            docs += len(res["files"])

    db.stage("score", "Checking if open postings are still online")
    closed = check_closed(db)

    if llm.enabled:
        for job in db.jobs("status = 'interview' AND prep = ''")[:3]:
            db.stage("gmail", f"Preparing your {job['company']} interview")
            try:
                db.update_job(job["id"], {"prep": make_prep(job, profile, llm)})
            except Exception as e:
                problems.append(f"prep {job['id']}: {e}")

    gmail_changes = []
    if settings["gmail"].get("enabled"):
        db.stage("gmail", "Reading Gmail for replies")
        try:
            from .gmail_sync import sync
            gmail_changes = sync(db, settings.home, settings["gmail"].get("lookback_days", 3))
        except Exception as e:
            problems.append(f"gmail: {e}")

    shortlisted = sum(1 for j in new if (j.get("match") or 0) >= settings["tailor"]["min_match"] and j.get("lang") != "German needed")
    db.run_update(day, found=len(new), added=added, shortlisted=shortlisted, docs_made=docs,
                  gmail_updates=len(gmail_changes), notes="; ".join(problems)[:500])
    db.stage("done", f"Done: {len(new)} new jobs, {shortlisted} shortlisted")
    return {"new": added, "shortlisted": shortlisted, "docs": docs, "closed": closed,
            "gmail": gmail_changes, "problems": problems}
