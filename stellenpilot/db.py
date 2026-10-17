"""SQLite storage for jobs and runs. One file, no server."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  company TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  remote INTEGER NOT NULL DEFAULT 0,
  url TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  posted_at TEXT,
  found_at TEXT NOT NULL,
  job_type TEXT NOT NULL DEFAULT '',
  lang TEXT NOT NULL DEFAULT '',
  match INTEGER,
  fit TEXT NOT NULL DEFAULT '',
  why TEXT NOT NULL DEFAULT '',
  gaps TEXT NOT NULL DEFAULT '',
  gap_tags TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'new',
  status_source TEXT NOT NULL DEFAULT 'run',
  status_updated_at TEXT,
  status_note TEXT NOT NULL DEFAULT '',
  folder TEXT NOT NULL DEFAULT '',
  closed INTEGER NOT NULL DEFAULT 0,
  closed_at TEXT,
  interview_at TEXT,
  prep TEXT NOT NULL DEFAULT '',
  rating INTEGER,
  notes TEXT NOT NULL DEFAULT '',
  dedupe_key TEXT NOT NULL DEFAULT '',
  german_level TEXT NOT NULL DEFAULT '',
  summary_en TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS jobs_dedupe ON jobs(dedupe_key);
CREATE TABLE IF NOT EXISTS runs (
  date TEXT PRIMARY KEY,
  found INTEGER NOT NULL DEFAULT 0,
  added INTEGER NOT NULL DEFAULT 0,
  shortlisted INTEGER NOT NULL DEFAULT 0,
  docs_made INTEGER NOT NULL DEFAULT 0,
  gmail_updates INTEGER NOT NULL DEFAULT 0,
  notes TEXT NOT NULL DEFAULT '',
  stage TEXT NOT NULL DEFAULT 'done',
  stage_at TEXT,
  stage_note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS run_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  found INTEGER NOT NULL DEFAULT 0,
  added INTEGER NOT NULL DEFAULT 0,
  shortlisted INTEGER NOT NULL DEFAULT 0,
  docs_made INTEGER NOT NULL DEFAULT 0,
  gmail_updates INTEGER NOT NULL DEFAULT 0,
  notes TEXT NOT NULL DEFAULT ''
);
"""

STATUSES = ("new", "ready", "applied", "interview", "offer", "rejected", "skipped")
# Fields the user owns. The pipeline never overwrites them.
USER_FIELDS = ("rating", "notes")
EDITABLE = {"status", "status_note", "rating", "notes", "closed", "interview_at", "prep", "folder"}


# One clock everywhere: local time, the clock you live by. Timestamps keep their UTC offset
# ("2026-10-18T21:30:00+02:00"), so they stay exact across daylight saving changes and moves.
def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> str:
    return date.today().isoformat()


def local_day(stamp: str | None) -> str:
    """The local date (YYYY-MM-DD) of a stored timestamp, or "" if there is none.
    Older databases hold UTC stamps ("...+00:00"); they are converted, so a Sunday evening in
    Germany stays Sunday. Stamps without an offset are already local and only lose their time."""
    if not stamp:
        return ""
    try:
        t = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return stamp[:10]
    return (t.astimezone() if t.tzinfo else t).date().isoformat()


# ---------- migrations ----------
# The database file remembers which steps it has had in SQLite's built in `PRAGMA user_version`.
# On every start the steps it is missing run once, in order.
#
# Rules:
#   * Only append. Never edit, reorder or delete a step: users' databases already ran it.
#   * SCHEMA above is frozen. A new column or table goes in a new step here, not in SCHEMA,
#     so fresh and old databases reach the same shape the same way.
#   * Steps 1 and 2 check before acting because they replace checks that ran on every start
#     before versioning existed. Steps from 3 on can be plain SQL.

def _m1_jobs_extra_columns(conn: sqlite3.Connection) -> None:
    have = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    for col in ("german_level", "summary_en"):
        if col not in have:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")


def _m2_run_log_backfill(conn: sqlite3.Connection) -> None:
    # Before run_log existed, each day kept one row in runs and a second search the same day
    # overwrote it. Carry those day rows over once so the history starts complete.
    if not conn.execute("SELECT 1 FROM run_log LIMIT 1").fetchone():
        conn.execute(
            "INSERT INTO run_log (date, finished_at, found, added, shortlisted, docs_made, gmail_updates, notes) "
            "SELECT date, COALESCE(stage_at, date), found, added, shortlisted, docs_made, gmail_updates, notes "
            "FROM runs WHERE stage = 'done' ORDER BY date")


MIGRATIONS = [
    _m1_jobs_extra_columns,  # 1
    _m2_run_log_backfill,    # 2
]
SCHEMA_VERSION = len(MIGRATIONS)


def _version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


class DB:
    def __init__(self, path: Path | str):
        had_data = Path(path).is_file() and Path(path).stat().st_size > 0
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        if had_data and _version(self.conn) < SCHEMA_VERSION:
            self._backup(Path(path))
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _backup(self, path: Path) -> None:
        """Copy the database before upgrading it, so a bad step can be undone by hand."""
        dest = sqlite3.connect(str(path.with_name(f"{path.name}.bak-v{_version(self.conn)}")))
        with dest:
            self.conn.backup(dest)
        dest.close()

    def _migrate(self) -> None:
        """Run the steps this database has not had yet. Safe when several processes start at once:
        BEGIN IMMEDIATE takes the write lock, then the version is read again inside it."""
        if _version(self.conn) >= SCHEMA_VERSION:
            return
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            for step in range(_version(self.conn), SCHEMA_VERSION):
                MIGRATIONS[step](self.conn)
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    # ---------- jobs ----------
    def job_ids(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT id FROM jobs")}

    def dedupe_keys(self, since: str | None = None) -> set[str]:
        """Company plus title keys already on the board. With `since` (an ISO date) only keys found on
        or after that day count, so a role the company posts again months later is not dropped."""
        if since:
            rows = self.conn.execute("SELECT dedupe_key FROM jobs WHERE found_at >= ?", (since,))
        else:
            rows = self.conn.execute("SELECT dedupe_key FROM jobs")
        return {r[0] for r in rows if r[0]}

    def last_seen(self, key: str) -> dict | None:
        """The most recent earlier job with this company plus title key, if any."""
        row = self.conn.execute("SELECT found_at, status FROM jobs WHERE dedupe_key = ? "
                                "ORDER BY found_at DESC LIMIT 1", (key,)).fetchone()
        return dict(row) if row else None

    def insert_job(self, job: dict) -> bool:
        """Insert a new job. Returns False if the id already exists."""
        row = {
            "found_at": today(), "status": "new", "status_source": "run",
            "status_updated_at": now(), **job,
        }
        row["gap_tags"] = json.dumps(row.get("gap_tags") or [])
        row["remote"] = int(bool(row.get("remote")))
        cols = [c for c in row if c in self._columns()]
        sql = f"INSERT OR IGNORE INTO jobs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
        cur = self.conn.execute(sql, [row[c] for c in cols])
        self.conn.commit()
        return cur.rowcount == 1

    def update_job(self, job_id: str, fields: dict, *, by_user: bool = False) -> None:
        if not by_user:
            fields = {k: v for k, v in fields.items() if k not in USER_FIELDS}
        if "gap_tags" in fields:
            fields["gap_tags"] = json.dumps(fields["gap_tags"])
        cols = [c for c in fields if c in self._columns() and c != "id"]
        if not cols:
            return
        sql = f"UPDATE jobs SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?"
        self.conn.execute(sql, [fields[c] for c in cols] + [job_id])
        self.conn.commit()

    def mark_ready(self, job_id: str, folder: str, note: str) -> None:
        """Store the folder; move to 'ready' only if the user has not changed the status meanwhile."""
        self.conn.execute("UPDATE jobs SET folder = ? WHERE id = ?", (folder, job_id))
        self.conn.execute("UPDATE jobs SET status = 'ready', status_source = 'run', status_updated_at = ?, "
                          "status_note = ? WHERE id = ? AND status = 'new'", (now(), note, job_id))
        self.conn.commit()

    def set_status(self, job_id: str, status: str, *, source: str, note: str = "") -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status}")
        self.update_job(job_id, {"status": status, "status_source": source,
                                 "status_updated_at": now(), "status_note": note}, by_user=True)

    def jobs(self, where: str = "1=1", params: tuple = ()) -> list[dict]:
        rows = self.conn.execute(f"SELECT * FROM jobs WHERE {where} ORDER BY match DESC NULLS LAST, found_at DESC", params)
        out = []
        for r in rows:
            d = dict(r)
            d["gap_tags"] = json.loads(d["gap_tags"] or "[]")
            d["remote"] = bool(d["remote"])
            d["closed"] = bool(d["closed"])
            out.append(d)
        return out

    def job(self, job_id: str) -> dict | None:
        found = self.jobs("id = ?", (job_id,))
        return found[0] if found else None

    def _columns(self) -> set[str]:
        if not hasattr(self, "_cols"):
            self._cols = {r[1] for r in self.conn.execute("PRAGMA table_info(jobs)")}
        return self._cols

    # ---------- runs ----------
    def run_update(self, date: str, **fields) -> None:
        self.conn.execute("INSERT OR IGNORE INTO runs (date) VALUES (?)", (date,))
        if fields:
            cols = ", ".join(f"{k} = ?" for k in fields)
            self.conn.execute(f"UPDATE runs SET {cols} WHERE date = ?", [*fields.values(), date])
        self.conn.commit()

    def stage(self, stage: str, note: str = "") -> None:
        """Live progress for the dashboard's office scene."""
        self.run_update(today(), stage=stage, stage_at=now(), stage_note=note)

    def runs(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM runs ORDER BY date DESC")]

    def log_run(self, date: str, **fields) -> None:
        """Keep one row per finished search, so several searches on one day all stay in the history."""
        fields = {"date": date, "finished_at": now(), **fields}
        cols = ", ".join(fields)
        self.conn.execute(f"INSERT INTO run_log ({cols}) VALUES ({', '.join('?' * len(fields))})", list(fields.values()))
        self.conn.commit()

    def history(self, limit: int = 200) -> list[dict]:
        """Finished searches, newest first."""
        return [dict(r) for r in self.conn.execute("SELECT * FROM run_log ORDER BY id DESC LIMIT ?", (limit,))]
