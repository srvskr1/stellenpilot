"""The daily run: collect, score, tailor, sync Gmail. Writes live progress for the dashboard."""
from __future__ import annotations

import http.client
import logging
import urllib.error
from datetime import date, timedelta
import urllib.parse
import urllib.request

from . import sources
from .http import friendly_error
from .db import DB, today
from .llm import LLM, job_ad
from .score import profile_text, score_job, taste_summary
from .tailor import tailor_job, unsupported_claims
from .text import dedupe_key, title_excluded

log = logging.getLogger("stellenpilot")
# Sources with full descriptions first, so duplicates keep the richer copy.
ORDER = ["watchlist", "arbeitsagentur", "theirstack", "arbeitnow", "adzuna", "jobicy", "remotive"]


def repost_since(settings) -> str | None:
    """First day that still counts for duplicates. A company plus title seen before this day is treated
    as a new posting (companies repost the same Werkstudent role every semester). None: never repost."""
    try:
        days = int(settings["search"].get("repost_after_days", 45))
    except (TypeError, ValueError):
        days = 45
    return (date.today() - timedelta(days=days)).isoformat() if days > 0 else None


def collect(settings, db: DB) -> tuple[list[dict], list[str]]:
    enabled = [n for n in ORDER if settings["sources"].get(n) or (n == "watchlist" and (settings["watch"].get("companies") or settings["watch"].get("starter_list")))]
    since = repost_since(settings)
    known_ids, known_keys = db.job_ids(), db.dedupe_keys(since)
    excl = settings["search"].get("exclude_title_words", [])
    new, problems = [], []
    country = settings["search"]["country"].lower()
    for name in enabled:
        covered = getattr(sources.REGISTRY[name], "COUNTRIES", None)
        if covered and country not in covered:
            problems.append(f"{name} skipped: it does not cover country '{country}'")
            continue
        db.stage("collect", f"Searching {sources.REGISTRY[name].LABEL}")
        try:
            found = sources.REGISTRY[name].fetch(settings)
        except Exception as e:  # one broken source must not stop the run
            problems.append(f"{name}: {friendly_error(e)}")
            log.warning("source %s failed: %s", name, e)
            continue
        log.info("%s returned %d jobs", name, len(found))
        problems += [f"{name}: {p}" for p in getattr(sources.REGISTRY[name], "PROBLEMS", [])]
        for job in found:
            key = dedupe_key(job["company"], job["title"])
            if job["id"] in known_ids or key in known_keys or title_excluded(job["title"], excl):
                continue
            known_ids.add(job["id"])
            known_keys.add(key)
            job["dedupe_key"] = key
            prev = db.last_seen(key) if since else None
            if isinstance(prev, dict):
                job["status_note"] = f"Posted again. You first saw this role on {prev['found_at']} (status then: {prev['status']})."
            new.append(job)
    offline = [p for p in problems if "no internet" in p]
    if not new and len(offline) >= 2:  # every reachable source failed the same way: say it once
        problems = [p for p in problems if "no internet" not in p] + [
            "No source could be reached: your computer could not look up any website address. "
            "Check your internet connection, VPN or proxy, then run the search again."]
    return new, problems


def my_german_level(settings) -> str:
    """From config, else from the profile's languages ("German (A2)", "Deutsch: Muttersprache"), else A2."""
    import re
    from .text import normalize_level
    lvl = normalize_level(settings["language"].get("my_german_level"))
    if lvl:
        return lvl
    for entry in (settings.profile.get("person") or {}).get("languages") or []:
        if re.search(r"(?i)\b(german|deutsch)", str(entry)):
            lvl = normalize_level(re.sub(r"(?i)\b(german|deutsch)\w*", "", str(entry)))
            if lvl:
                return lvl
    return "A2"


def check_closed(db: DB, limit: int = 15) -> int:
    """Mark jobs whose posting now returns 404 or 410. Other errors are ignored (could be temporary)."""
    import random
    from .manual import NO_FETCH, AddError, FetchError, open_public
    closed = 0
    open_jobs = db.jobs("status IN ('new', 'ready') AND closed = 0 AND url != ''")
    # A different sample each run, so every posting gets checked over time, not only the top matches.
    for job in random.sample(open_jobs, min(limit, len(open_jobs))):
        host = (urllib.parse.urlsplit(job["url"]).hostname or "").lower()
        if any(b in host for b in NO_FETCH):
            continue  # sites that forbid automated access are never fetched, not even to check
        try:
            open_public(job["url"], max_bytes=1, timeout=15)  # public pages only, checked on every redirect
        except FetchError as e:
            if e.status in (404, 410):
                db.update_job(job["id"], {"closed": 1, "closed_at": today()})
                closed += 1
        except (AddError, OSError, http.client.HTTPException):
            pass  # refused, offline or a broken server: try again another day
    return closed


PREP_SYSTEM = """Write an interview prep pack for the candidate. Plain text, each heading on its own line starting with "## ", bullets starting with "- ".
Headings: "## About <company>" (2 to 4 lines, only what the ad says, no outside facts), "## What they will test", "## Likely questions" (6 to 8),
"## Your stories" (3 to 5 STAR stories built ONLY from the candidate's real experience, one bullet each), "## Your gaps and how to answer", "## Questions to ask them" (3 to 4).
Under 3500 characters. Do not use hyphens or dashes as punctuation inside sentences.
Return JSON: {"prep": "..."}"""


def make_prep(job: dict, profile: dict, llm) -> str:
    user = f"CANDIDATE\n{profile_text(profile)}\n\nJOB\n{job['title']} at {job['company']}\n{job_ad(job.get('description', ''), llm.max_chars)}"
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
    try:
        return _run(settings, db, tailor)
    finally:
        db.conn.close()
        if settings["llm"].get("provider") == "builtin":
            from . import builtin
            builtin.stop()  # free the memory right away; it starts again in seconds when needed


def _run(settings, db: DB, tailor: bool) -> dict:
    profile = settings.profile
    if not profile:
        raise RuntimeError("profile.toml is missing. Run `stellenpilot init` and fill it in.")
    llm = LLM(settings)
    day = today()
    db.run_update(day, notes="")
    db.stage("collect", "Starting the daily search")

    new, problems = collect(settings, db)
    from .score import profile_gaps
    if gaps := profile_gaps(profile):
        problems.insert(0, gaps)

    db.stage("score", f"Scoring {len(new)} new jobs against your CV")
    taste = taste_summary(db.jobs("rating IS NOT NULL"))
    added = 0
    lang_cfg = settings["language"]
    skip_de = lang_cfg.get("skip_if_german_too_high", lang_cfg.get("skip_if_fluent_german_required", True))
    my_de, tol = my_german_level(settings), int(lang_cfg.get("german_tolerance", 1))
    ai_ids = None
    if llm.enabled and llm.ai_job_limit and len(new) > llm.ai_job_limit:
        from .score import keyword_score
        ranked = sorted(new, key=lambda j: keyword_score(j, profile)["match"], reverse=True)
        ai_ids = {j["id"] for j in ranked[:llm.ai_job_limit]}
        db.stage("score", f"Scoring {len(new)} new jobs; the AI reads the {llm.ai_job_limit} most promising")
    for i, job in enumerate(new, 1):
        use = llm if ai_ids is None or job["id"] in ai_ids else None
        if use and llm.local and i % 5 == 0:
            db.stage("score", f"Scoring new jobs with the AI on this computer ({i} of {len(new)})")
        try:
            job.update(score_job(job, profile, use, taste, skip_de, my_de, tol))
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
                res = tailor_job(job, profile, out_root, llm, t.get("make_pdf", True), t.get("letter_language", "auto"), my_de)
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
    from .notify import send_digest
    problems += send_digest(settings, db, {"new": added, "shortlisted": shortlisted, "gmail": gmail_changes,
                                           "problems": problems}, day)
    db.run_update(day, found=len(new), added=added, shortlisted=shortlisted, docs_made=docs,
                  gmail_updates=len(gmail_changes), notes="; ".join(problems)[:500])
    db.stage("done", f"Done: {len(new)} new jobs, {shortlisted} shortlisted")
    return {"new": added, "shortlisted": shortlisted, "docs": docs, "closed": closed,
            "gmail": gmail_changes, "problems": problems}
