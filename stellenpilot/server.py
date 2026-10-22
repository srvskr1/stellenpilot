"""Local dashboard server on the standard library. Binds to 127.0.0.1 only."""
from __future__ import annotations

import json
import re
import os
import math
import subprocess
import sys
import threading
from collections import Counter
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import unquote

from . import schedule
from .db import DB, STATUSES, local_day
from .score import lifts, unlocks

CAMEL = {"id": "_id", "status_source": "statusSource", "status_updated_at": "statusUpdatedAt",
         "status_note": "statusNote", "gap_tags": "gapTags", "cv_style": "cvStyle", "interview_at": "interviewAt",
         "found_at": "foundAt", "posted_at": "postedAt", "job_type": "jobType", "closed_at": "closedAt",
         "german_level": "germanLevel", "summary_en": "summaryEn", "docs_made": "docsMade", "gmail_updates": "gmailUpdates", "stage_at": "stageAt", "stage_note": "stageNote",
         "finished_at": "finishedAt"}
SENT = {"applied", "interview", "offer", "rejected"}
LOCAL_NAMES = {"127.0.0.1", "localhost", "[::1]"}
SLOW_POSTS = {"/api/add", "/api/gmail", "/api/gmail/imap", "/api/cv/import", "/api/cv/reread", "/api/gmail/connect", "/api/builtin/test"}
# What the Settings page may change. Types come from config.DEFAULTS.
EDITABLE = {"search": ("keywords", "city", "radius_km", "country", "include_remote", "max_age_days", "exclude_title_words"),
            "sources": ("arbeitsagentur", "arbeitnow", "adzuna", "theirstack", "jobicy", "remotive", "workingstudentjobs"),
            "llm": ("provider", "model", "base_url"),
            "language": ("my_german_level",),
            "tailor": ("min_match", "letter_language", "cv_style"),
            "schedule": ("enabled", "time"),
            "watch": ("starter_list",),
            "ui": ("language", "check_updates")}
CHOICES = {("llm", "provider"): {"none", "builtin", "ollama", "lmstudio", "llamacpp", "vllm", "local", "anthropic", "openai"},
           ("language", "my_german_level"): {"", "A1", "A2", "B1", "B2", "C1", "C2"},
           ("tailor", "letter_language"): {"auto", "en", "de"},
           ("tailor", "cv_style"): {"classic", "compact", "lebenslauf"},
           ("ui", "language"): {"auto", "en", "de"}}
SECRETS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "THEIRSTACK_API_KEY")


_TRUE, _FALSE = {"true", "1", "yes", "on"}, {"false", "0", "no", "off", ""}


def _as_bool(v, name: str) -> bool:
    """bool("false") is True in Python, so text is read by its meaning. Anything else is refused."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and v in (0, 1):
        return bool(v)
    if isinstance(v, str) and v.strip().lower() in _TRUE | _FALSE:
        return v.strip().lower() in _TRUE
    if v is None:
        return False
    raise ValueError(f"{name.replace('_', ' ')} must be on or off")


def clean_settings(body: dict) -> dict:
    """Keep only editable fields, with the type the default has. Raises ValueError with a friendly message."""
    from .config import DEFAULTS
    out = {}
    for section, keys in EDITABLE.items():
        given = body.get(section)
        if not isinstance(given, dict):
            continue
        for k in keys:
            if k not in given:
                continue
            want, v = DEFAULTS[section][k], given[k]
            if isinstance(want, bool):
                v = _as_bool(v, k)
            elif isinstance(want, int):
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    raise ValueError(f"{k.replace('_', ' ')} must be a whole number") from None
                if not 0 <= v <= 1000:
                    raise ValueError(f"{k.replace('_', ' ')} must be between 0 and 1000")
            elif isinstance(want, list):
                v = [str(x).strip()[:120] for x in (v if isinstance(v, list) else []) if str(x).strip()][:50]
            else:
                v = str(v or "").strip()[:300]
            if (section, k) in CHOICES and v not in CHOICES[(section, k)]:
                raise ValueError(f"unknown {k.replace('_', ' ')}: {v}")
            out.setdefault(section, {})[k] = v
    if "country" in out.get("search", {}):
        out["search"]["country"] = out["search"]["country"].lower()
        if not (len(out["search"]["country"]) == 2 and out["search"]["country"].isalpha()):
            raise ValueError("country must be a two letter code, for example de")
    if "time" in out.get("schedule", {}):
        from .schedule import ScheduleError, parse_time
        try:
            h, m = parse_time(out["schedule"]["time"])
        except ScheduleError as e:
            raise ValueError(str(e)) from None
        out["schedule"]["time"] = f"{h:02d}:{m:02d}"
    if "search" in out and "keywords" in out["search"] and not out["search"]["keywords"]:
        raise ValueError("add at least one job title to search for")
    return out
CV_TYPES = {".pdf", ".docx", ".txt", ".md"}
MAX_CV_BYTES = 10_000_000


def camel(d: dict) -> dict:
    return {CAMEL.get(k, k): v for k, v in d.items() if k not in ("description", "dedupe_key")}


def weekly_summary(jobs: list[dict], today: date | None = None) -> list[dict]:
    """This week's numbers, computed from the jobs table. Weeks start on Monday, local time."""
    today = today or date.today()
    start = today - timedelta(days=today.weekday())
    in_week = [j for j in jobs if local_day(j.get("status_updated_at")) >= start.isoformat()]
    gaps = Counter(t for j in jobs if (j.get("match") or 0) > 0 for t in j.get("gap_tags", []) if t != "German")
    applied = sum(1 for j in in_week if j["status"] == "applied")
    replies = sum(1 for j in in_week if j["status"] in ("interview", "offer", "rejected"))
    interviews = sum(1 for j in in_week if j["status"] in ("interview", "offer"))
    ready = [j["company"] for j in jobs if j["status"] == "ready" and not j["closed"]]
    tips = []
    if applied < 5:
        tips.append(f"You sent {applied} application{'s' if applied != 1 else ''} this week; about 5 a week keeps the pipeline moving.")
    if ready:
        tips.append(f"{len(ready)} tailored CV{'s are' if len(ready) > 1 else ' is'} waiting: {', '.join(ready[:4])}.")
    top = gaps.most_common(1)
    if top:
        tips.append(f"{top[0][0]} is the gap named most often, so it is the best skill to learn next.")
    return [{"weekOf": start.isoformat(), "applied": applied, "replies": replies, "interviews": interviews,
             "topGap": top[0][0] if top else "", "summary": " ".join(tips)}]


STAGE = {"applied": 1, "interview": 2, "offer": 3}
FOLLOW_UP_DAYS = 14


def _reached(j: dict) -> int:
    """How far an application got: 1 sent, 2 interview, 3 offer. Imported rows may lack the column."""
    r = j.get("reached") or (j["status"] if j["status"] in STAGE else "applied" if j["status"] == "rejected" else "")
    return STAGE.get(r, 0)


def diagnosis(jobs: list[dict], today: date | None = None) -> dict:
    """Where applications stop, said in one sentence, plus interviews gone quiet and the hidden German count.
    Thresholds are rules of thumb, not statistics; the numbers are shown next to the sentence."""
    today = today or date.today()
    sent = [j for j in jobs if _reached(j)]
    interviews = sum(1 for j in sent if _reached(j) >= 2)
    offers = sum(1 for j in sent if _reached(j) == 3)
    answered = sum(1 for j in sent if _reached(j) >= 2 or j["status"] == "rejected")
    n = len(sent)
    if n < 10:
        stage, text = "early", "Fewer than 10 applications so far, too early to say where they stop."
    elif answered == 0:
        stage, text = "silent", "No company has answered yet. That points at your CV or the jobs you pick, not at interviews. If Gmail is not connected, mark replies by hand so this stays right."
    elif interviews == 0 or interviews / n < 0.05:
        stage, text = "screening", "Companies answer, but almost none invite you. Your CV is read and loses at the first check: compare it with the ads that turned you down."
    elif offers == 0 and interviews >= 3:
        stage, text = "interview", "You get interviews but no offer yet. Your CV works; practise for the interviews."
    else:
        stage, text = "ok", "Your applications move through every step. Keep the pace."
    quiet = []
    for j in jobs:
        if j["status"] != "interview" or j.get("closed"):
            continue
        last = max(local_day(j.get("status_updated_at")), (j.get("interview_at") or "")[:10])
        days = (today - date.fromisoformat(last)).days if last else 0
        if days >= FOLLOW_UP_DAYS:
            quiet.append({"id": j["id"], "company": j["company"], "title": j["title"], "days": days})
    from .text import ad_language
    since = (today - timedelta(days=90)).isoformat()
    english = [j for j in jobs if (j.get("found_at") or "") >= since
               and ad_language(j["title"] + "\n" + (j.get("description") or "")) == "en"]
    return {"sent": n, "answered": answered, "interviews": interviews, "offers": offers,
            "stage": stage, "text": text, "followUps": sorted(quiet, key=lambda q: -q["days"]),
            "englishAds": len(english),
            "englishAskB2": sum(1 for j in english if j.get("german_level") in ("B2", "C1", "C2"))}


def _sync_closing(sync, settings):
    own = DB(settings.db_path)
    try:
        return sync(own, settings.home, settings["gmail"].get("lookback_days", 3), settings=settings)
    finally:
        own.conn.close()


def open_in_file_manager(path: str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 (local desktop action requested by the user)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def gmail_status(settings) -> dict:
    from .gmail_sync import install_command, install_command_full, packages_installed
    home = Path(settings.home)
    from .mail_imap import SECRET
    cfg = settings["gmail"]
    imap = cfg.get("method") == "imap"
    return {"enabled": bool(cfg.get("enabled")),
            "method": "imap" if imap else "oauth",
            "address": cfg.get("address", "") if imap else "",
            "imapHost": cfg.get("imap_host", "") if imap else "",
            "passwordSaved": bool(settings.secret(SECRET)),
            "packages": packages_installed(),
            "installCommand": install_command(),
            "installCommandFull": install_command_full(),
            "credentials": (home / "credentials.json").exists(),
            "connected": bool(settings.secret(SECRET)) if imap else (home / "token.json").exists()}


def shortcut_status() -> dict:
    from . import shortcut
    if schedule.in_docker():
        return {"supported": False, "exists": False}
    try:
        return {"supported": True, "exists": shortcut.exists()}
    except Exception:
        return {"supported": True, "exists": False}


def check_credentials(text: str) -> str:
    """Validate a Google OAuth client file; return it unchanged. Raises ValueError in plain words."""
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError("That is not the file from Google. It should be a .json file.") from None
    client = data.get("installed") if isinstance(data, dict) else None
    if not isinstance(client, dict) or not client.get("client_id") or not client.get("client_secret"):
        if isinstance(data, dict) and "web" in data:
            raise ValueError("This is a Web application client. Create one of type Desktop app instead.")
        raise ValueError("This file is not a Google OAuth client of type Desktop app.")
    return text


def fill_skills(jobs: list[dict], profile: dict) -> None:
    """The tools the ad names that the profile has, for jobs scored before this was stored.

    New jobs carry the list from the scoring run. For the older ones it is worked out here,
    so the dashboard can show the skills of every job, not only the newest.
    """
    if not profile:
        return
    from .score import skill_overlap
    for j in jobs:
        if j.get("skills") or not j.get("description"):
            continue
        overlap, _ = skill_overlap(j, profile)
        j["skills"] = overlap


def fill_lifts(jobs: list[dict], profile: dict) -> None:
    """"With dbt this job would score 78" for open keyword scored jobs below the match line."""
    for j in jobs:
        j["lift"] = lifts(j, profile) if profile and not j.get("closed") else []


def find_doc(job, kind: str, out_root: Path) -> Path | None:
    """The CV or cover letter in a job's folder, PDF first. Only inside the output folder."""
    if not job or not job["folder"] or kind not in ("cv", "letter"):
        return None
    folder = Path(job["folder"]).resolve()
    if not folder.is_dir() or out_root not in folder.parents:
        return None
    marks = ("_CV_",) if kind == "cv" else ("_Cover_Letter_", "_Anschreiben_")
    found = [f for f in folder.iterdir() if any(m in f.name for m in marks) and f.suffix in (".pdf", ".docx")]
    return min(found, key=lambda f: f.suffix != ".pdf", default=None)


def reread_offer(settings) -> bool:
    """True when an AI is on, the profile has no jobs or projects, and the CV text is still on disk."""
    from .importer import saved_cv_text
    p = settings.profile or {}
    return ((settings["llm"].get("provider") or "none") != "none"
            and not (p.get("experience") or p.get("projects"))
            and bool(saved_cv_text(settings.home).strip()))


def with_language(page: bytes, choice) -> bytes:
    """Tell the page which language the user picked. Only a known value is ever written into the HTML."""
    choice = choice if choice in CHOICES[("ui", "language")] else "auto"
    return page.replace(b'<html lang="en">', f'<html lang="en" data-ui="{choice}">'.encode(), 1)


def make_handler(settings, port: int = 8765):
    db = DB(settings.db_path)
    run_state = {"running": False, "result": None, "error": ""}
    lock = threading.Lock()  # one SQLite connection, so one request at a time touches it

    page = resources.files("stellenpilot").joinpath("web/index.html").read_bytes()
    icon = resources.files("stellenpilot").joinpath("web/icon.png").read_bytes()
    fonts = {f"/fonts/{n}": resources.files("stellenpilot").joinpath(f"web/fonts/{n}").read_bytes()
             for n in ("Geist-Variable.woff2", "GeistMono-Variable.woff2")}
    out_root = (settings.home / settings["tailor"]["output_dir"]).resolve()

    def subtitle():
        s = settings["search"]
        return f"{', '.join(s['keywords'][:2])} near {s['city']}" + (" and remote" if s.get("include_remote") else "")

    def background_run():
        from .pipeline import run
        try:
            res = run(settings)
            run_state.update(result={k: res[k] for k in ("new", "shortlisted", "docs", "problems")}, error="")
        except Exception as e:  # shown on the dashboard instead of a traceback
            run_state.update(result=None, error=str(e) or e.__class__.__name__)
        finally:
            run_state["running"] = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        @staticmethod
        def _local(hostport: str | None) -> bool:
            # Port is ignored on purpose, so Docker port mappings work.
            host = (hostport or "").rsplit(":", 1)[0] if not (hostport or "").startswith("[") else (hostport or "").split("]")[0] + "]"
            return host in LOCAL_NAMES

        def _host_ok(self) -> bool:
            # Blocks DNS rebinding: a page on another domain that resolves to 127.0.0.1
            # still sends its own host name, which is refused here.
            if not self._local(self.headers.get("Host")):
                self._send(403, {"error": "unexpected Host header"})
                return False
            return True

        def _guard(self) -> bool:
            # A custom header forces a CORS preflight, which this server never answers,
            # so other websites cannot change your data through your browser.
            if not self._host_ok():
                return False
            origin = self.headers.get("Origin")
            if self.headers.get("X-Jobhunt") != "1" or (origin and not self._local(origin.split("//")[-1])):
                self._send(403, {"error": "request refused"})
                return False
            return True

        def _body(self, limit: int = 1_000_000) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0 or n > limit:
                raise ValueError("bad Content-Length")
            data = json.loads(self.rfile.read(n) or b"{}") if n else {}
            if not isinstance(data, dict):
                raise ValueError("body must be a JSON object")
            return data

        def do_GET(self):
            if not self._host_ok():
                return
            if self.path.startswith("/api/progress"):  # polled while slow AI work runs, so no lock
                from urllib.parse import parse_qs, urlsplit
                from . import progress
                task = (parse_qs(urlsplit(self.path).query).get("task") or [""])[0]
                return self._send(200, progress.snapshot(task))
            if self.path == "/api/update":  # asks GitHub at most once a day, may wait 10 s, so no lock
                from . import update
                return self._send(200, update.status(settings.home, bool(settings["ui"].get("check_updates", True))))
            if self.path == "/api/check":  # may wait up to 10 s for a local model server, so no lock
                from .cli import setup_checks
                return self._send(200, {"checks": setup_checks(settings)})
            with lock:
                self._get()

        def do_PATCH(self):
            if not self._guard():
                return
            with lock:
                self._patch()

        def do_POST(self):
            if not self._guard():
                return
            if self.path in SLOW_POSTS or self.path.startswith("/api/docs/"):
                # Adding a job (fetch, AI scoring, maybe tailoring) and Gmail sync can take minutes with a
                # local model. They use their own database connection so the dashboard stays responsive.
                return self._post()
            with lock:
                self._post()

        def _get(self):
            if self.path in ("/", "/index.html"):
                return self._send(200, with_language(page, settings["ui"].get("language")), "text/html; charset=utf-8")
            if self.path == "/icon.png":
                return self._send(200, icon, "image/png")
            if self.path in fonts:
                return self._send(200, fonts[self.path], "font/woff2")
            if self.path == "/api/state":
                jobs = db.jobs()
                fill_skills(jobs, settings.profile)
                fill_lifts(jobs, settings.profile)
                return self._send(200, {
                    "jobs": [camel(j) for j in jobs],
                    "runs": [camel(r) for r in db.runs()],
                    "history": [camel(r) for r in db.history()],
                    "weekly": weekly_summary(jobs),
                    "unlocks": unlocks(jobs, settings.profile, settings["tailor"]["min_match"]),
                    "diagnosis": diagnosis(jobs),
                    "gmailEnabled": bool(settings["gmail"].get("enabled")),
                    "subtitle": subtitle(),
                    "firstName": (str(settings.profile.get("person", {}).get("name") or "").split() or [""])[0],
                    "run": run_state,
                    "schedule": settings["schedule"],
                    "search": settings["search"],
                    "profileReady": bool(settings.profile) and settings.profile.get("person", {}).get("name") != "Alex Example",
                })
            if self.path == "/api/settings":
                return self._send(200, {**{sec: {k: settings[sec][k] for k in keys} for sec, keys in EDITABLE.items()},
                                        "keys": {k: bool(settings.secret(k)) for k in SECRETS},
                                        "scheduleActive": schedule.is_enabled(settings.home),
                                        "inDocker": schedule.in_docker(),
                                        "gmail": gmail_status(settings),
                                        "shortcut": shortcut_status(),
                                        "rereadOffer": reread_offer(settings)})
            if self.path == "/api/builtin":
                from . import builtin
                return self._send(200, builtin.status(settings["llm"].get("model") or "standard"))
            if self.path == "/api/cv":
                return self._send(200, {"profile": settings.profile,
                                        "isExample": settings.profile.get("person", {}).get("name") == "Alex Example"})
            self._send(404, {"error": "not found"})

        def _patch(self):
            if not self.path.startswith("/api/jobs/"):
                return self._send(404, {"error": "not found"})
            job_id = unquote(self.path[len("/api/jobs/"):])
            if not db.job(job_id):
                return self._send(404, {"error": "unknown job"})
            try:
                body = self._body()
                if "status" in body:
                    if body["status"] not in STATUSES:
                        raise ValueError("bad status")
                    db.set_status(job_id, body["status"], source="manual", note=str(body.get("statusNote", "")))
                fields = {}
                if "rating" in body:
                    r = body["rating"]
                    if isinstance(r, dict) or r in (None, 0):
                        fields["rating"] = None
                    elif isinstance(r, (int, float)) and math.isfinite(r):
                        fields["rating"] = 1 if r > 0 else -1
                    else:
                        raise ValueError("rating must be 1, -1 or null")
                if "notes" in body:
                    fields["notes"] = str(body["notes"])[:5000]
                if "closed" in body:
                    fields["closed"] = int(_as_bool(body["closed"], "closed"))
                if fields:
                    db.update_job(job_id, fields, by_user=True)
            except (ValueError, TypeError, OverflowError) as e:
                return self._send(400, {"error": str(e)})
            self._send(200, {"ok": True})

        def _post(self):
            if self.path.startswith("/api/open-folder/"):
                job = db.job(unquote(self.path[len("/api/open-folder/"):]))
                folder = Path(job["folder"]).resolve() if job and job["folder"] else None
                if not folder or not folder.is_dir() or out_root not in folder.parents:
                    return self._send(400, {"error": "No document folder for this job yet"})
                open_in_file_manager(str(folder))
                return self._send(200, {"ok": True})
            if self.path.startswith("/api/open-doc/"):
                job_id, _, kind = unquote(self.path[len("/api/open-doc/"):]).rpartition("/")
                doc = find_doc(db.job(job_id), kind, out_root)
                if not doc:
                    return self._send(400, {"error": "This document is not there yet"})
                open_in_file_manager(str(doc))
                return self._send(200, {"ok": True})
            if self.path.startswith("/api/docs/"):
                from .manual import AddError, make_docs
                from . import progress
                own = DB(settings.db_path)
                job_id = unquote(self.path[len("/api/docs/"):])
                try:
                    with progress.track("docs:" + job_id, "Writing your CV and cover letter"):
                        make_docs(settings, own, job_id)
                except progress.Busy:
                    return self._send(409, {"error": "These documents are already being written."})
                except AddError as e:
                    return self._send(400, {"error": str(e)})
                except Exception as e:
                    return self._send(500, {"error": f"Could not make the documents: {e}"})
                finally:
                    own.conn.close()
                return self._send(200, {"ok": True})
            if self.path == "/api/add":
                from .manual import AddError, add_job
                try:
                    body = self._body()
                    own = DB(settings.db_path)
                    try:
                        res = add_job(settings, own, tailor=_as_bool(body.get("tailor"), "tailor"),
                                      **{k: str(body.get(k) or "") for k in ("url", "text", "title", "company", "location")})
                    finally:
                        own.conn.close()
                except (AddError, ValueError) as e:
                    return self._send(400, {"error": str(e)})
                except Exception as e:
                    return self._send(500, {"error": f"Could not add the job: {e}"})
                return self._send(200, {"status": res["status"], "job": camel(res["job"])})
            if self.path == "/api/run":
                if run_state["running"]:
                    return self._send(409, {"error": "A search is already running."})
                run_state.update(running=True, result=None, error="")
                threading.Thread(target=background_run, daemon=True).start()
                return self._send(200, {"ok": True})
            if self.path == "/api/settings":
                from .config import save_secrets, save_user_config
                try:
                    body = self._body()
                    updates = clean_settings(body)
                    keys = body.get("keys") if isinstance(body.get("keys"), dict) else {}
                    clear = body.get("clear_keys") if isinstance(body.get("clear_keys"), list) else []
                    save_secrets(settings.home, {k: str(keys.get(k) or "") for k in SECRETS},
                                 clear=[k for k in clear if k in SECRETS])
                    note = ""
                    want = {**settings["schedule"], **updates.get("schedule", {})}
                    if "schedule" in updates:
                        if want["enabled"]:
                            note = schedule.enable(settings.home, want["time"])
                        elif settings["schedule"].get("enabled") or schedule.is_enabled(settings.home):
                            schedule.disable(settings.home)
                    settings.cfg = save_user_config(settings.home, updates)
                except (ValueError, schedule.ScheduleError) as e:
                    return self._send(400, {"error": str(e)})
                return self._send(200, {"ok": True, "scheduleNote": note, "rereadOffer": reread_offer(settings)})
            if self.path == "/api/cv/import":
                return self._cv_import()
            if self.path == "/api/cv/save":
                return self._cv_save()
            if self.path == "/api/cv/reread":
                return self._cv_reread()
            if self.path.startswith("/api/builtin/"):
                from . import builtin
                try:
                    key = str(self._body().get("model") or "standard")
                except (ValueError, TypeError) as e:
                    return self._send(400, {"error": str(e)})
                if key not in builtin.MODELS:
                    return self._send(400, {"error": "unknown model"})
                action = self.path[len("/api/builtin/"):]
                if action == "download":
                    builtin.start_download(key)
                    return self._send(200, builtin.status(key))
                if action == "test":
                    try:
                        return self._send(200, {"speed": builtin.speed_test(key)})
                    except Exception as e:
                        return self._send(400, {"error": str(e)})
                if action == "remove":
                    if run_state["running"]:
                        return self._send(409, {"error": "Wait until the search is finished."})
                    try:
                        builtin.remove()
                    except RuntimeError as e:
                        return self._send(409, {"error": str(e)})
                    return self._send(200, builtin.status(key))
                return self._send(404, {"error": "not found"})
            if self.path == "/api/shortcut":
                from . import shortcut
                try:
                    where = shortcut.create(settings.home)
                except Exception as e:
                    return self._send(400, {"error": f"Could not create the icon: {e}"})
                return self._send(200, {"path": str(where), "shortcut": shortcut_status()})
            if self.path == "/api/gmail/credentials":
                try:
                    text = check_credentials(str(self._body().get("text") or ""))
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                from .config import write_private
                write_private(settings.home / "credentials.json", text)
                (settings.home / "token.json").unlink(missing_ok=True)  # a new client needs a new consent
                return self._send(200, {"gmail": gmail_status(settings)})
            if self.path == "/api/gmail/connect":
                from .config import save_user_config
                settings.cfg["gmail"] = {**settings["gmail"], "method": "oauth"}
                from .gmail_sync import _service
                try:
                    _service(settings.home)  # opens Google's consent page in the browser on this computer
                except Exception as e:
                    return self._send(400, {"error": f"Could not connect Gmail: {e}"})
                settings.cfg = save_user_config(settings.home, {"gmail": {"enabled": True, "method": "oauth"}})
                return self._send(200, {"gmail": gmail_status(settings)})
            if self.path == "/api/gmail/imap":
                # The simple way: address and app password. Logs in once, read only, to check them.
                from .config import save_secrets, save_user_config
                from . import mail_imap
                try:
                    body = self._body()
                    address = str(body.get("address") or "").strip()
                    password = str(body.get("password") or "").strip()
                    given = str(body.get("host") or "").strip()
                    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address):
                        raise mail_imap.MailError("Enter your full email address.")
                    if given and not re.fullmatch(r"[A-Za-z0-9.-]+", given):
                        raise mail_imap.MailError("The mail server name looks wrong, for example imap.gmx.net.")
                    password = password or (settings.secret(mail_imap.SECRET) or "")
                    if not password:
                        raise mail_imap.MailError("Paste the app password.")
                    host = mail_imap.host_for(address, given)
                    mail_imap.check(host, address, password)
                except mail_imap.MailError as e:
                    return self._send(400, {"error": str(e)})
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                save_secrets(settings.home, {mail_imap.SECRET: "".join(password.split())})
                settings.cfg = save_user_config(settings.home, {"gmail": {"enabled": True, "method": "imap",
                                                                          "address": address, "imap_host": given}})
                return self._send(200, {"gmail": gmail_status(settings)})
            if self.path == "/api/gmail/disconnect":
                from .config import save_secrets, save_user_config
                from .mail_imap import SECRET
                (settings.home / "token.json").unlink(missing_ok=True)
                save_secrets(settings.home, {}, clear=[SECRET])  # forget the app password too
                settings.cfg = save_user_config(settings.home, {"gmail": {"enabled": False, "method": "", "address": ""}})
                return self._send(200, {"gmail": gmail_status(settings)})
            if self.path == "/api/gmail":
                if not settings["gmail"].get("enabled"):
                    return self._send(400, {"error": "Gmail is not connected. Connect it under Settings, Gmail."})
                try:
                    from .gmail_sync import sync
                    return self._send(200, {"changes": _sync_closing(sync, settings)})
                except Exception as e:
                    return self._send(500, {"error": str(e)})
            self._send(404, {"error": "not found"})

        def _cv_import(self):
            import base64
            import tempfile
            from .importer import import_cv, read_cv_text
            try:
                body = self._body(limit=MAX_CV_BYTES * 4 // 3 + 4096)
                suffix = Path(str(body.get("name") or "")).suffix.lower()
                if suffix not in CV_TYPES:
                    raise ValueError("Use a PDF, DOCX, TXT or MD file.")
                data = base64.b64decode(str(body.get("data") or ""), validate=True)
                if not data:
                    raise ValueError("The file is empty.")
            except (ValueError, TypeError) as e:
                return self._send(400, {"error": str(e)})
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / ("cv" + suffix)
                path.write_bytes(data)
                from . import progress
                try:
                    with progress.track("cv", "Reading your CV"):
                        out, notes = import_cv(path, settings)
                    cv_text = read_cv_text(path)
                except progress.Busy:
                    return self._send(409, {"error": "Your CV is already being read. Wait until it is finished."})
                except (RuntimeError, ValueError) as e:
                    return self._send(400, {"error": str(e)})
                except OSError as e:
                    return self._send(502, {"error": f"Could not reach the AI model ({e}). Is it running? Check with: stellenpilot doctor"})
                except Exception as e:
                    return self._send(500, {"error": f"Import failed: {e.__class__.__name__}: {e}"})
            import tomllib
            return self._send(200, {"profile": tomllib.loads(out.read_text(encoding="utf-8")), "notes": notes, "cvText": cv_text})

        def _cv_reread(self):
            """Read the saved CV again with the AI that was just turned on. Only replaces a profile
            that has no jobs or projects yet, so nothing you typed under My CV is lost."""
            import tomllib
            from .importer import import_text, saved_cv_text
            from .llm import LLM
            if not reread_offer(settings):
                return self._send(400, {"error": "Nothing to read again: turn on an AI first, and this only works "
                                                 "while your profile has no jobs or projects."})
            from . import progress
            try:
                if not LLM(settings).enabled:
                    raise RuntimeError("Turn on an AI first.")
                with progress.track("cv", "Reading your CV again"):
                    out, notes = import_text(saved_cv_text(settings.home), settings)
            except progress.Busy:
                return self._send(409, {"error": "Your CV is already being read. Wait until it is finished."})
            except RuntimeError as e:
                return self._send(400, {"error": str(e)})
            except OSError as e:
                return self._send(502, {"error": f"Could not reach the AI model ({e}). Is it running? Check with: stellenpilot doctor"})
            except Exception as e:
                return self._send(500, {"error": f"Reading the CV failed: {e.__class__.__name__}: {e}"})
            profile = tomllib.loads(out.read_text(encoding="utf-8"))
            if not (profile.get("experience") or profile.get("projects")):
                return self._send(422, {"error": "The AI could not read your jobs or projects either. Add them under My CV.",
                                        "notes": notes})
            from .importer import to_toml
            with lock:
                now = settings.profile or {}
                if now.get("experience") or now.get("projects"):
                    # Filled in meanwhile (by you, or by another read): never overwrite it.
                    return self._send(409, {"error": "Your profile was filled in meanwhile, so it was left as it is.",
                                            "profile": now})
                prof = settings.home / "profile.toml"
                if prof.exists():
                    prof.replace(settings.home / "profile.backup.toml")
                prof.write_text(to_toml(profile, None), encoding="utf-8")
                settings.profile = tomllib.loads(prof.read_text(encoding="utf-8"))
            return self._send(200, {"profile": settings.profile, "notes": notes})

        def _cv_save(self):
            import tomllib
            from .importer import _shape, to_toml
            try:
                given = self._body(limit=2_000_000).get("profile")
                if not isinstance(given, dict):
                    raise ValueError("profile missing")
                profile = _shape(given)
                person = given.get("person") if isinstance(given.get("person"), dict) else {}
                profile["person"] = {k: ([str(x).strip() for x in person.get(k) or [] if str(x).strip()] if k in ("links", "languages", "headlines")
                                         else str(person.get(k) or "").strip())
                                     for k in ("name", "email", "phone", "location", "links", "languages", "headlines", "summary")}
                if not profile["person"]["name"]:
                    raise ValueError("Add your name first.")
                text = to_toml(profile, None)
                data = tomllib.loads(text)
            except (ValueError, TypeError) as e:
                return self._send(400, {"error": str(e)})
            prof = settings.home / "profile.toml"
            if prof.exists():
                prof.replace(settings.home / "profile.backup.toml")
            prof.write_text(text, encoding="utf-8")
            settings.profile = data  # the next search and added job use the new profile
            return self._send(200, {"ok": True})

    def catch_up():
        # A laptop asleep at the scheduled time misses the run; do it once the dashboard is open.
        # Check and claim under the same lock as Search now, so the two can never start two runs at once.
        with lock:
            if run_state["running"]:
                return
            last = max((r["date"] for r in db.runs()), default=None)
            if not schedule.missed_today(settings, last):
                return
            run_state.update(running=True, result=None, error="")
        threading.Thread(target=background_run, daemon=True).start()

    Handler.catch_up = staticmethod(catch_up)
    Handler.close = staticmethod(db.conn.close)  # releases the dashboard's database connection
    return Handler


def _already_running(port: int) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=3) as r:  # noqa: S310
            return r.status == 200 and b'"jobs"' in r.read(200)
    except OSError:
        return False


def serve(settings, port: int = 8765, host: str = "127.0.0.1", open_browser: bool = True) -> None:
    # The Host header check below still only accepts 127.0.0.1 and localhost, so even when
    # Docker listens on all interfaces inside the container, only your own browser gets in.
    import webbrowser
    url = f"http://127.0.0.1:{port}"
    open_browser = open_browser and not os.environ.get("STELLENPILOT_NO_BROWSER") and not schedule.in_docker()
    handler = make_handler(settings, port)
    try:
        httpd = ThreadingHTTPServer((host, port), handler)
    except OSError:
        if _already_running(port):  # double clicked the icon twice: just show the open one
            print(f"Stellenpilot is already running at {url}. Opening it in your browser.", flush=True)
            if open_browser:
                webbrowser.open(url)
            return
        raise SystemExit(f"Port {port} is used by another program. Start with: stellenpilot serve --port {port + 1}") from None

    def watch():
        while True:
            try:
                handler.catch_up()
            except Exception:  # never let the watcher stop the dashboard
                pass
            threading.Event().wait(600)
    threading.Thread(target=watch, daemon=True).start()
    if settings["schedule"].get("enabled"):
        try:  # keeps the daily task pointing at this install, e.g. after an update or a rename
            schedule.enable(settings.home, settings["schedule"]["time"])
        except Exception as e:
            print(f"Note: could not refresh the automatic search ({e}). Open Settings and save to fix it.", flush=True)
    print(f"Stellenpilot running at {url}  (close this window or press Ctrl+C to stop)", flush=True)
    if open_browser:
        threading.Timer(0.8, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        handler.close()
