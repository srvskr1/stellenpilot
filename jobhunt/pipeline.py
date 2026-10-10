"""The daily run: collect, score, tailor, sync Gmail. Writes live progress for the dashboard."""
from __future__ import annotations

import logging
from pathlib import Path

from . import sources
from .db import DB, today
from .llm import LLM
from .score import score_job, taste_summary
from .tailor import tailor_job
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
    skip_de = settings["language"].get("skip_if_fluent_german_required", True)
    for job in new:
        try:
            job.update(score_job(job, profile, llm, taste, skip_de))
        except Exception as e:
            problems.append(f"scoring {job['id']}: {e}")
            continue
        db.insert_job(job)

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
            db.update_job(job["id"], {"folder": res["folder"], "status": "ready",
                                      "status_note": f"CV covers {res['coverage']}% of the ad"})
            docs += len(res["files"])

    gmail_changes = []
    if settings["gmail"].get("enabled"):
        db.stage("gmail", "Reading Gmail for replies")
        try:
            from .gmail_sync import sync
            gmail_changes = sync(db, settings.home, settings["gmail"].get("lookback_days", 3))
        except Exception as e:
            problems.append(f"gmail: {e}")

    shortlisted = sum(1 for j in new if (j.get("match") or 0) >= settings["tailor"]["min_match"] and j.get("lang") != "German needed")
    db.run_update(day, found=len(new), added=len(new), shortlisted=shortlisted, docs_made=docs,
                  gmail_updates=len(gmail_changes), notes="; ".join(problems)[:500])
    db.stage("done", f"Done: {len(new)} new jobs, {shortlisted} shortlisted")
    return {"new": len(new), "shortlisted": shortlisted, "docs": docs,
            "gmail": gmail_changes, "problems": problems}
