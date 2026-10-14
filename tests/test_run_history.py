"""Search history keeps every search, not one row per day (issue #14)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from stellenpilot.db import DB


class RunHistoryTest(unittest.TestCase):
    def test_two_searches_on_one_day_both_stay(self):
        with tempfile.TemporaryDirectory() as d:
            db = DB(Path(d) / "j.db")
            db.log_run("2026-10-13", found=4, shortlisted=1)
            db.log_run("2026-10-14", found=10, shortlisted=2)
            db.log_run("2026-10-14", found=3, shortlisted=0, notes="second search")
            h = db.history()
            self.assertEqual([r["found"] for r in h], [3, 10, 4])  # newest first
            self.assertEqual(h[0]["notes"], "second search")
            self.assertIn("T", h[0]["finished_at"])  # a time, so two runs on one day can be told apart

    def test_old_day_rows_carry_over_once(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "j.db"
            # A database from before run_log existed.
            con = sqlite3.connect(path)
            con.executescript("""
              CREATE TABLE runs (date TEXT PRIMARY KEY, found INTEGER NOT NULL DEFAULT 0, added INTEGER NOT NULL DEFAULT 0,
                shortlisted INTEGER NOT NULL DEFAULT 0, docs_made INTEGER NOT NULL DEFAULT 0, gmail_updates INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '', stage TEXT NOT NULL DEFAULT 'done', stage_at TEXT, stage_note TEXT NOT NULL DEFAULT '');
              INSERT INTO runs (date, found, stage, stage_at) VALUES ('2026-10-12', 7, 'done', '2026-10-12T07:00:00+00:00');
              INSERT INTO runs (date, found, stage) VALUES ('2026-10-13', 5, 'done');
              INSERT INTO runs (date, found, stage) VALUES ('2026-10-14', 0, 'score');""")
            con.commit()
            con.close()
            db = DB(path)
            self.assertEqual([r["date"] for r in db.history()], ["2026-10-13", "2026-10-12"])  # unfinished run left out
            db.conn.close()
            self.assertEqual(len(DB(path).history()), 2)  # not copied again on the next start


if __name__ == "__main__":
    unittest.main()
