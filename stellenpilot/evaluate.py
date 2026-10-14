"""Measure how well the scoring ranks the jobs you actually care about.

`stellenpilot eval` compares each scorer (the score stored at search time, keyword scoring, your
configured AI and any other AI you name) against labels: your thumbs up and down, jobs that reached
an interview or offer, or a CSV you filled in by hand. It answers three questions:

* Ranking: do good jobs get higher scores? (Spearman correlation, ROC AUC, precision at k)
* Decision: does `tailor.min_match` let the good jobs through and keep the rest out?
* Health: does the model use the whole scale, how often does it fail, and how slow is it?

Everything is computed with the standard library, so it runs wherever Stellenpilot runs.
"""
from __future__ import annotations

import copy
import csv
import json
import math
import random
import statistics
import time
from datetime import datetime
from pathlib import Path

from .db import DB
from .score import keyword_score, score_job

POSITIVE_STATUSES = ("interview", "offer")
# No score column: seeing the old score while labeling would pull your labels toward it.
SHEET_FIELDS = ["id", "label", "title", "company", "location", "url"]


# ---------------------------------------------------------------- labels

def labels_from_db(db: DB, include_rejected: bool = False) -> dict[str, float]:
    """1 for a thumbs up or an interview or offer, 0 for a thumbs down. A rejection says more about
    the competition than about fit, so it only counts as 0 with include_rejected."""
    out: dict[str, float] = {}
    for j in db.jobs("rating IS NOT NULL OR status IN ('interview', 'offer', 'rejected')"):
        pos = j.get("rating") == 1 or j["status"] in POSITIVE_STATUSES
        neg = j.get("rating") == -1 or (include_rejected and j["status"] == "rejected")
        if pos and neg:
            continue  # you disliked it but got an interview, or liked it and got rejected: no clean label
        if pos:
            out[j["id"]] = 1.0
        elif neg:
            out[j["id"]] = 0.0
    return out


def labels_from_csv(path: Path) -> dict[str, float]:
    """A sheet with at least the columns id and label. Labels can be 0/1 or a grade like 0 to 3.
    Rows with an empty label are ignored, so a half filled sheet works."""
    out: dict[str, float] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "id" not in reader.fieldnames or "label" not in reader.fieldnames:
            raise ValueError(f"{path.name} needs the columns id and label")
        for row in reader:
            raw = (row.get("label") or "").strip()
            if not raw:
                continue
            try:
                out[row["id"].strip()] = float(raw)
            except ValueError:
                raise ValueError(f"{path.name}: label '{raw}' for {row['id']} is not a number") from None
    return out


def make_sheet(db: DB, path: Path, n: int = 100, seed: int = 7) -> int:
    """Write jobs to label by hand, spread evenly over the stored scores. Sampling only the top
    matches would hide whether low scores are really bad, so each score band gets its share."""
    jobs = [j for j in db.jobs("match IS NOT NULL AND description != ''")]
    rng = random.Random(seed)
    bands: dict[int, list[dict]] = {}
    for j in jobs:
        bands.setdefault(min(int(j["match"]) // 20, 4), []).append(j)
    for b in bands.values():
        rng.shuffle(b)
    picked: list[dict] = []
    while len(picked) < n and any(bands.values()):
        for key in sorted(bands):
            if bands[key] and len(picked) < n:
                picked.append(bands[key].pop())
    rng.shuffle(picked)  # do not show the stored score order while labeling
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_FIELDS)
        w.writeheader()
        for j in picked:
            w.writerow({"id": j["id"], "label": "", "title": j["title"], "company": j["company"],
                        "location": j["location"], "url": j["url"]})
    return len(picked)


# ---------------------------------------------------------------- statistics

def ranks(xs: list[float]) -> list[float]:
    """1 based ranks, ties get the average rank."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None  # a constant score (or label) has no correlation
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)


def spearman(scores: list[float], labels: list[float]) -> float | None:
    return pearson(ranks(scores), ranks(labels))


def auc(scores: list[float], positive: list[bool]) -> float | None:
    """Chance that a random good job scores higher than a random bad one (ties count half)."""
    n_pos = sum(positive)
    n_neg = len(positive) - n_pos
    if not n_pos or not n_neg:
        return None
    r = ranks(scores)
    rank_sum = sum(ri for ri, p in zip(r, positive, strict=True) if p)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def precision_at_k(scores: list[float], positive: list[bool], k: int) -> float | None:
    if not scores:
        return None
    k = min(k, len(scores))
    top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return sum(positive[i] for i in top) / k


def bootstrap_ci(fn, scores: list[float], labels: list[float], n: int = 1000, seed: int = 1) -> tuple[float, float] | None:
    """95 percent interval by resampling jobs. Wide intervals mean you need more labels before
    trusting a difference between two models."""
    rng = random.Random(seed)
    idx = range(len(scores))
    vals = []
    for _ in range(n):
        pick = [rng.choice(idx) for _ in idx]
        v = fn([scores[i] for i in pick], [labels[i] for i in pick])
        if v is not None:
            vals.append(v)
    if len(vals) < n // 2:
        return None
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def metrics(scores: list[float], labels: list[float], *, threshold: float, min_match: int, k: int) -> dict:
    positive = [lab >= threshold for lab in labels]
    passed = [s >= min_match for s in scores]
    good_passed = sum(p and g for p, g in zip(passed, positive, strict=True))
    auc_fn = lambda s, lab: auc(s, [x >= threshold for x in lab])  # noqa: E731
    return {
        "n": len(scores),
        "positives": sum(positive),
        "spearman": spearman(scores, labels),
        "spearman_ci": bootstrap_ci(spearman, scores, labels),
        "auc": auc(scores, positive),
        "auc_ci": bootstrap_ci(auc_fn, scores, labels),
        f"precision_at_{k}": precision_at_k(scores, positive, k),
        "base_rate": sum(positive) / len(positive) if positive else None,
        # The decision the pipeline makes: which jobs get a tailored CV.
        "passed_min_match": sum(passed),
        "recall_at_min_match": good_passed / sum(positive) if sum(positive) else None,
        "precision_at_min_match": good_passed / sum(passed) if sum(passed) else None,
        "score_spread": statistics.pstdev(scores) if scores else None,
        "distinct_scores": len(set(scores)),
    }


# ---------------------------------------------------------------- scorers

def parse_provider(spec: str) -> dict:
    """'ollama:qwen3.5:4b' -> provider ollama, model qwen3.5:4b. 'anthropic' keeps its default model."""
    provider, _, model = spec.partition(":")
    return {"provider": provider.strip().lower(), "model": model.strip()}


def settings_with_llm(settings, spec: dict):
    """A copy of the settings with another [llm] section, keeping base_url and limits from the
    original only when the provider is the same."""
    s = copy.copy(settings)
    base = dict(settings["llm"]) if settings["llm"].get("provider") == spec["provider"] else {}
    llm = {**base, "provider": spec["provider"]}
    if spec.get("model"):
        llm["model"] = spec["model"]
    s.cfg = {**settings.cfg, "llm": llm}
    return s


def run_scorer(name: str, jobs: list[dict], profile: dict, llm=None, progress=None) -> dict:
    """Score every job with one method. Returns scores in job order plus failures and timing.
    No taste summary is given: the taste comes from the same thumbs used as labels, which would
    let the model see the answers."""
    scores, failed, secs = [], 0, []
    for i, job in enumerate(jobs, 1):
        if progress:
            progress(name, i, len(jobs))
        t0 = time.perf_counter()
        if name == "stored":
            scores.append(float(job.get("match") or 0))
            continue
        if llm is None:
            res = keyword_score(job, profile)
        else:
            res = score_job(job, profile, llm, taste="", skip_german=False)
            if "AI scoring failed" in res.get("why", ""):
                failed += 1
        secs.append(time.perf_counter() - t0)
        scores.append(float(res["match"]))
    return {"scores": scores, "failed": failed, "seconds_per_job": statistics.fmean(secs) if secs else 0.0}


# ---------------------------------------------------------------- the whole evaluation

def evaluate(settings, *, labels_csv: Path | None = None, providers: list[str] | None = None,
             use_config_llm: bool = True, include_rejected: bool = False, limit: int = 0,
             threshold: float | None = None, k: int = 10, out_dir: Path | None = None,
             progress=None) -> dict:
    from .llm import LLM
    db = DB(settings.db_path)
    try:
        labels = labels_from_csv(labels_csv) if labels_csv else labels_from_db(db, include_rejected)
        jobs = [j for j in (db.job(i) for i in labels) if j]
    finally:
        db.conn.close()
    if limit and len(jobs) > limit:
        jobs = random.Random(3).sample(jobs, limit)
    if not jobs:
        raise ValueError("No labeled jobs yet. Give some jobs a thumbs up or down in the dashboard, "
                         "or fill a sheet made with: stellenpilot eval --make-sheet")
    y = [labels[j["id"]] for j in jobs]
    if threshold is None:
        threshold = 1.0 if set(y) <= {0.0, 1.0} else (min(y) + max(y)) / 2
    good = sum(v >= threshold for v in y)
    if good == 0 or good == len(y):
        raise ValueError(f"All {len(y)} labeled jobs are {'good' if good else 'bad'} matches, so there is nothing to rank. "
                         "Label some of both kinds (thumbs up and thumbs down), or fill a sheet made with: "
                         "stellenpilot eval --make-sheet")
    min_match = int(settings["tailor"].get("min_match", 70))

    plan: list[tuple[str, object]] = [("stored", None), ("keyword", None)]
    specs = []
    if use_config_llm and (settings["llm"].get("provider") or "none") != "none":
        specs.append({"provider": settings["llm"]["provider"], "model": settings["llm"].get("model", "")})
    specs += [parse_provider(p) for p in providers or []]
    seen = set()
    for spec in specs:
        llm = LLM(settings_with_llm(settings, spec))
        label = f"{llm.provider}:{llm.model}"
        if label not in seen:
            seen.add(label)
            plan.append((label, llm))

    results, rows = {}, {j["id"]: {"id": j["id"], "label": labels[j["id"]], "title": j["title"], "company": j["company"]} for j in jobs}
    for name, llm in plan:
        try:
            run = run_scorer("stored" if name == "stored" else name, jobs, settings.profile, llm, progress)
        finally:
            if llm is not None and getattr(llm, "provider", "") == "builtin":
                from . import builtin
                builtin.stop()
        m = metrics(run["scores"], y, threshold=threshold, min_match=min_match, k=k)
        m.update(failed=run["failed"], seconds_per_job=round(run["seconds_per_job"], 2))
        results[name] = m
        for j, s in zip(jobs, run["scores"], strict=True):
            rows[j["id"]][name] = s

    report = {"created": datetime.now().isoformat(timespec="seconds"),
              "labels": "csv:" + labels_csv.name if labels_csv else ("db+rejected" if include_rejected else "db"),
              "n_jobs": len(jobs), "positive_threshold": threshold, "min_match": min_match, "k": k,
              "results": results}
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        names = [n for n, _ in plan]
        with open(out_dir / "scores.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "label", "title", "company", *names])
            w.writeheader()
            w.writerows(rows.values())
        report["out_dir"] = str(out_dir)
    return report


def _fmt(v, pct: bool = False) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:.0f}%" if pct else f"{v:.2f}"


def format_report(report: dict) -> str:
    k = report["k"]
    lines = [f"{report['n_jobs']} labeled jobs ({report['labels']}), "
             f"good job = label >= {report['positive_threshold']:g}, min_match = {report['min_match']}", ""]
    head = f"{'scorer':28} {'spearman':>9} {'AUC':>6} {'P@' + str(k):>6} {'recall':>7} {'precision':>9} {'spread':>7} {'fail':>5} {'s/job':>6}"
    lines += [head, "-" * len(head)]
    for name, m in report["results"].items():
        lines.append(f"{name[:28]:28} {_fmt(m['spearman']):>9} {_fmt(m['auc']):>6} {_fmt(m[f'precision_at_{k}'], True):>6} "
                     f"{_fmt(m['recall_at_min_match'], True):>7} {_fmt(m['precision_at_min_match'], True):>9} "
                     f"{m['score_spread']:>7.1f} {m['failed']:>5} {m['seconds_per_job']:>6.1f}")
    first = next(iter(report["results"].values()))
    lines += ["", f"Base rate: {_fmt(first['base_rate'], True)} of these jobs are good. A useful scorer has AUC well above 0.5 "
              f"and P@{k} well above the base rate.",
              "recall and precision are for the jobs that pass min_match, which are the ones that get a tailored CV."]
    for name, m in report["results"].items():
        if m["distinct_scores"] <= 2 and m["n"] >= 5:
            lines.append(f"Warning: {name} gave only {m['distinct_scores']} different scores. It cannot rank jobs.")
        ci = m.get("auc_ci")
        if ci and ci[1] - ci[0] > 0.25:
            lines.append(f"Note: {name} AUC could be anywhere from {ci[0]:.2f} to {ci[1]:.2f}. Label more jobs before comparing models.")
    if report["n_jobs"] < 30:
        lines.append("Fewer than 30 labeled jobs: treat these numbers as a first look, not a verdict.")
    if report.get("out_dir"):
        lines.append(f"\nSaved report.json and scores.csv in {report['out_dir']}")
    return "\n".join(lines)


def default_out_dir(home: Path) -> Path:
    return home / "eval" / datetime.now().strftime("%Y-%m-%d_%H%M%S")
