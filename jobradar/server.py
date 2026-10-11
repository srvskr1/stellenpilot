"""Local dashboard server on the standard library. Binds to 127.0.0.1 only."""
from __future__ import annotations

import json
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
from .db import DB, STATUSES

CAMEL = {"id": "_id", "status_source": "statusSource", "status_updated_at": "statusUpdatedAt",
         "status_note": "statusNote", "gap_tags": "gapTags", "interview_at": "interviewAt",
         "found_at": "foundAt", "posted_at": "postedAt", "job_type": "jobType", "closed_at": "closedAt",
         "german_level": "germanLevel", "summary_en": "summaryEn", "docs_made": "docsMade", "gmail_updates": "gmailUpdates", "stage_at": "stageAt", "stage_note": "stageNote"}
SENT = {"applied", "interview", "offer", "rejected"}
LOCAL_NAMES = {"127.0.0.1", "localhost", "[::1]"}
SLOW_POSTS = {"/api/add", "/api/gmail", "/api/cv/import"}
# What the Settings page may change. Types come from config.DEFAULTS.
EDITABLE = {"search": ("keywords", "city", "radius_km", "country", "include_remote", "max_age_days", "exclude_title_words"),
            "sources": ("arbeitsagentur", "arbeitnow", "adzuna", "theirstack"),
            "llm": ("provider", "model", "base_url"),
            "language": ("my_german_level",),
            "tailor": ("min_match", "letter_language"),
            "schedule": ("enabled", "time")}
CHOICES = {("llm", "provider"): {"none", "ollama", "lmstudio", "llamacpp", "vllm", "local", "anthropic", "openai"},
           ("language", "my_german_level"): {"", "A1", "A2", "B1", "B2", "C1", "C2"},
           ("tailor", "letter_language"): {"auto", "en", "de"}}
SECRETS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "THEIRSTACK_API_KEY")


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
                v = bool(v)
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


def weekly_summary(jobs: list[dict]) -> list[dict]:
    """This week's numbers, computed from the jobs table."""
    start = date.today() - timedelta(days=date.today().weekday())
    in_week = [j for j in jobs if (j.get("status_updated_at") or "")[:10] >= start.isoformat()]
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


def _sync_closing(sync, settings):
    own = DB(settings.db_path)
    try:
        return sync(own, settings.home, settings["gmail"].get("lookback_days", 3))
    finally:
        own.conn.close()


def open_in_file_manager(path: str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 (local desktop action requested by the user)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def make_handler(settings, port: int = 8765):
    db = DB(settings.db_path)
    run_state = {"running": False, "result": None, "error": ""}
    lock = threading.Lock()  # one SQLite connection, so one request at a time touches it

    page = resources.files("jobradar").joinpath("web/index.html").read_bytes()
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
            if self.path in SLOW_POSTS:
                # Adding a job (fetch, AI scoring, maybe tailoring) and Gmail sync can take minutes with a
                # local model. They use their own database connection so the dashboard stays responsive.
                return self._post()
            with lock:
                self._post()

        def _get(self):
            if self.path in ("/", "/index.html"):
                return self._send(200, page, "text/html; charset=utf-8")
            if self.path == "/api/state":
                jobs = db.jobs()
                return self._send(200, {
                    "jobs": [camel(j) for j in jobs],
                    "runs": [camel(r) for r in db.runs()],
                    "weekly": weekly_summary(jobs),
                    "gmailEnabled": bool(settings["gmail"].get("enabled")),
                    "subtitle": subtitle(),
                    "run": run_state,
                    "schedule": settings["schedule"],
                    "profileReady": bool(settings.profile) and settings.profile.get("person", {}).get("name") != "Alex Example",
                })
            if self.path == "/api/settings":
                return self._send(200, {**{sec: {k: settings[sec][k] for k in keys} for sec, keys in EDITABLE.items()},
                                        "keys": {k: bool(settings.secret(k)) for k in SECRETS},
                                        "scheduleActive": schedule.is_enabled(settings.home),
                                        "inDocker": schedule.in_docker()})
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
                    fields["closed"] = int(bool(body["closed"]))
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
            if self.path == "/api/add":
                from .manual import AddError, add_job
                try:
                    body = self._body()
                    own = DB(settings.db_path)
                    try:
                        res = add_job(settings, own, tailor=bool(body.get("tailor")),
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
                    save_secrets(settings.home, {k: str(keys.get(k) or "") for k in SECRETS})
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
                return self._send(200, {"ok": True, "scheduleNote": note})
            if self.path == "/api/cv/import":
                return self._cv_import()
            if self.path == "/api/cv/save":
                return self._cv_save()
            if self.path == "/api/gmail":
                if not settings["gmail"].get("enabled"):
                    return self._send(400, {"error": "Gmail sync is off. See docs/gmail.md"})
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
                try:
                    out, notes = import_cv(path, settings)
                    cv_text = read_cv_text(path)
                except (RuntimeError, ValueError) as e:
                    return self._send(400, {"error": str(e)})
                except OSError as e:
                    return self._send(502, {"error": f"Could not reach the AI model ({e}). Is it running? Check with: jobradar doctor"})
                except Exception as e:
                    return self._send(500, {"error": f"Import failed: {e.__class__.__name__}: {e}"})
            import tomllib
            return self._send(200, {"profile": tomllib.loads(out.read_text(encoding="utf-8")), "notes": notes, "cvText": cv_text})

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
        if run_state["running"]:
            return
        with lock:
            last = max((r["date"] for r in db.runs()), default=None)
        if schedule.missed_today(settings, last):
            run_state.update(running=True, result=None, error="")
            threading.Thread(target=background_run, daemon=True).start()

    Handler.catch_up = staticmethod(catch_up)
    return Handler


def serve(settings, port: int = 8765, host: str = "127.0.0.1") -> None:
    # The Host header check below still only accepts 127.0.0.1 and localhost, so even when
    # Docker listens on all interfaces inside the container, only your own browser gets in.
    handler = make_handler(settings, port)
    httpd = ThreadingHTTPServer((host, port), handler)

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
    print(f"JobRadar running at http://127.0.0.1:{port}  (Ctrl+C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
