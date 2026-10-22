"""Where applications stop: the reached column, the diagnosis sentence, follow ups, hidden German."""
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from stellenpilot.db import DB
from stellenpilot.server import diagnosis

TODAY = date(2026, 10, 22)


def app(i, status, reached="", updated="2026-10-01T10:00:00+02:00", **kw):
    return {"id": f"a{i}", "company": f"Co {i}", "title": "Data Engineer", "status": status, "reached": reached,
            "status_updated_at": updated, "closed": 0, "found_at": "2026-10-01", "description": "", **kw}


class ReachedTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.db = DB(Path(self.d.name) / "j.db")
        self.db.insert_job({"id": "x", "source": "t", "title": "DE", "company": "C", "location": "", "url": "", "description": ""})

    def tearDown(self):
        self.db.conn.close()
        self.d.cleanup()

    def test_rejection_keeps_the_furthest_step(self):
        for s in ("applied", "interview", "rejected"):
            self.db.set_status("x", s, source="manual")
        self.assertEqual(self.db.job("x")["reached"], "interview")

    def test_moving_back_to_ready_clears_it(self):
        self.db.set_status("x", "applied", source="manual")
        self.db.set_status("x", "ready", source="manual")
        self.assertEqual(self.db.job("x")["reached"], "")

    def test_old_database_is_backfilled(self):
        path = Path(self.d.name) / "old.db"
        DB(path).conn.close()
        con = sqlite3.connect(path)
        con.execute("ALTER TABLE jobs DROP COLUMN reached")  # a database from before the column existed
        con.execute("INSERT INTO jobs (id, source, title, found_at, status, interview_at) VALUES ('r1', 't', 'x', '2026-01-01', 'rejected', '2026-02-01')")
        con.execute("INSERT INTO jobs (id, source, title, found_at, status, interview_at) VALUES ('r2', 't', 'x', '2026-01-01', 'rejected', NULL)")
        con.commit()
        con.close()
        db = DB(path)
        self.assertEqual((db.job("r1")["reached"], db.job("r2")["reached"]), ("interview", "applied"))
        db.conn.close()


class DiagnosisTests(unittest.TestCase):
    def test_silence_points_at_the_cv(self):
        self.assertEqual(diagnosis([app(i, "applied", "applied") for i in range(12)], TODAY)["stage"], "silent")

    def test_rejections_without_interviews_is_screening(self):
        jobs = [app(i, "rejected", "applied") for i in range(12)]
        self.assertEqual(diagnosis(jobs, TODAY)["stage"], "screening")

    def test_interviews_without_offers(self):
        jobs = [app(i, "rejected", "interview") for i in range(4)] + [app(10 + i, "applied", "applied") for i in range(8)]
        d = diagnosis(jobs, TODAY)
        self.assertEqual((d["stage"], d["interviews"], d["answered"]), ("interview", 4, 4))

    def test_quiet_interview_gets_a_follow_up(self):
        jobs = [app(1, "interview", "interview", updated="2026-10-01T10:00:00+02:00"),
                app(2, "interview", "interview", updated="2026-10-20T10:00:00+02:00")]
        self.assertEqual([q["id"] for q in diagnosis(jobs, TODAY)["followUps"]], ["a1"])

    def test_counts_english_ads_that_ask_for_b2(self):
        en = "We are looking for a data engineer. You will work with our team and you have experience with Python."
        jobs = [app(1, "new", description=en, german_level="C1"), app(2, "new", description=en, german_level="")]
        d = diagnosis(jobs, TODAY)
        self.assertEqual((d["englishAds"], d["englishAskB2"]), (2, 1))


if __name__ == "__main__":
    unittest.main()
