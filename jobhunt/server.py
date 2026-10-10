"""Local dashboard server on the standard library. Binds to 127.0.0.1 only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import unquote

from .db import DB, STATUSES

CAMEL = {"id": "_id", "status_source": "statusSource", "status_updated_at": "statusUpdatedAt",
         "status_note": "statusNote", "gap_tags": "gapTags", "interview_at": "interviewAt",
         "found_at": "foundAt", "posted_at": "postedAt", "job_type": "jobType", "closed_at": "closedAt",
         "docs_made": "docsMade", "gmail_updates": "gmailUpdates", "stage_at": "stageAt", "stage_note": "stageNote"}
SENT = {"applied", "interview", "offer", "rejected"}


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


def open_in_file_manager(path: str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 (local desktop action requested by the user)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def make_handler(settings):
    db = DB(settings.db_path)
    page = resources.files("jobhunt").joinpath("web/index.html").read_bytes()
    out_root = (settings.home / settings["tailor"]["output_dir"]).resolve()
    s = settings["search"]
    subtitle = f"{', '.join(s['keywords'][:2])} near {s['city']}" + (" and remote" if s.get("include_remote") else "")

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

        def _guard(self) -> bool:
            # A custom header forces a CORS preflight, which this server never answers,
            # so other websites cannot change your data through your browser.
            if self.headers.get("X-Jobhunt") != "1":
                self._send(403, {"error": "missing X-Jobhunt header"})
                return False
            return True

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self._send(200, page, "text/html; charset=utf-8")
            if self.path == "/api/state":
                jobs = db.jobs()
                return self._send(200, {
                    "jobs": [camel(j) for j in jobs],
                    "runs": [camel(r) for r in db.runs()],
                    "weekly": weekly_summary(jobs),
                    "gmailEnabled": bool(settings["gmail"].get("enabled")),
                    "subtitle": subtitle,
                })
            self._send(404, {"error": "not found"})

        def do_PATCH(self):
            if not self._guard():
                return
            if not self.path.startswith("/api/jobs/"):
                return self._send(404, {"error": "not found"})
            job_id = unquote(self.path[len("/api/jobs/"):])
            if not db.job(job_id):
                return self._send(404, {"error": "unknown job"})
            body = self._body()
            try:
                if "status" in body:
                    if body["status"] not in STATUSES:
                        raise ValueError("bad status")
                    db.set_status(job_id, body["status"], source="manual", note=str(body.get("statusNote", "")))
                fields = {}
                if "rating" in body:
                    r = body["rating"]
                    fields["rating"] = None if isinstance(r, dict) or r in (None, 0) else (1 if int(r) > 0 else -1)
                if "notes" in body:
                    fields["notes"] = str(body["notes"])[:5000]
                if "closed" in body:
                    fields["closed"] = int(bool(body["closed"]))
                if fields:
                    db.update_job(job_id, fields, by_user=True)
            except (ValueError, TypeError) as e:
                return self._send(400, {"error": str(e)})
            self._send(200, {"ok": True})

        def do_POST(self):
            if not self._guard():
                return
            if self.path.startswith("/api/open-folder/"):
                job = db.job(unquote(self.path[len("/api/open-folder/"):]))
                folder = Path(job["folder"]).resolve() if job and job["folder"] else None
                if not folder or not folder.is_dir() or out_root not in folder.parents:
                    return self._send(400, {"error": "No document folder for this job yet"})
                open_in_file_manager(str(folder))
                return self._send(200, {"ok": True})
            if self.path == "/api/gmail":
                if not settings["gmail"].get("enabled"):
                    return self._send(400, {"error": "Gmail sync is off. See docs/gmail.md"})
                try:
                    from .gmail_sync import sync
                    return self._send(200, {"changes": sync(db, settings.home, settings["gmail"].get("lookback_days", 3))})
                except Exception as e:
                    return self._send(500, {"error": str(e)})
            self._send(404, {"error": "not found"})

    return Handler


def serve(settings, port: int = 8765) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(settings))
    print(f"Job Hunt Board running at http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
