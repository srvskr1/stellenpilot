"""`stellenpilot demo` (issue #21): fictional jobs that show every part of the dashboard, no keys or network."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from stellenpilot.config import Settings
from stellenpilot.db import DB, STATUSES
from stellenpilot.demo import SAMPLES, load_demo


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.settings = Settings(Path(self.tmp.name))
        self.n = load_demo(self.settings)
        self.db = DB(self.settings.db_path)

    def tearDown(self):
        self.db.conn.close()
        self.tmp.cleanup()

    def test_loads_every_sample_with_a_valid_status(self):
        jobs = self.db.jobs()
        self.assertEqual(self.n, len(SAMPLES))
        self.assertEqual(len(jobs), len(SAMPLES))
        self.assertTrue(all(j["status"] in STATUSES for j in jobs))
        # Enough variety to show every board column worth demonstrating.
        self.assertLessEqual({"new", "ready", "applied", "interview", "rejected", "skipped"}, {j["status"] for j in jobs})
        self.assertTrue(all(j["dedupe_key"] and j["found_at"] and j["posted_at"] for j in jobs))

    def test_data_is_fictional(self):
        for j in self.db.jobs():
            self.assertTrue(j["url"].startswith("https://example.com/"), j["url"])

    def test_interview_is_at_eight_local_time(self):
        job = next(j for j in self.db.jobs() if j["status"] == "interview")
        at = datetime.fromisoformat(job["interview_at"])
        self.assertEqual(at.utcoffset(), at.astimezone().utcoffset())  # stored in local time (#18)
        self.assertEqual((at.hour, at.minute, at.second), (8, 0, 0))

    def test_history_has_a_finished_run(self):
        self.assertEqual(self.db.runs()[0]["stage"], "done")
        self.assertEqual(self.db.history()[0]["notes"], "Demo data")

    def test_dashboard_serves_the_demo(self):
        from helpers import fetch_json, running
        from stellenpilot.server import make_handler
        with running(make_handler(self.settings)) as srv:
            state = fetch_json(f"{srv.base}/api/state")
        self.assertEqual(len(state["jobs"]), len(SAMPLES))
        self.assertEqual(state["history"][0]["notes"], "Demo data")


if __name__ == "__main__":
    unittest.main()
