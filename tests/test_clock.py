"""One clock everywhere (issue #18): stored timestamps are local with their offset, and dates
are always taken in local time, also from older databases that hold UTC stamps."""
import os
import tempfile
import time
import unittest
from datetime import date, datetime
from pathlib import Path

from stellenpilot.db import DB, local_day, now, today
from stellenpilot.server import weekly_summary


class BerlinTime(unittest.TestCase):
    def setUp(self):
        self._tz = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/Berlin"
        time.tzset()

    def tearDown(self):
        if self._tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._tz
        time.tzset()


@unittest.skipUnless(hasattr(time, "tzset"), "needs time.tzset (not on Windows)")
class ClockTests(BerlinTime):
    def test_now_is_local_with_its_offset(self):
        stamp = datetime.fromisoformat(now())
        self.assertIsNotNone(stamp.tzinfo)
        self.assertEqual(stamp.utcoffset(), datetime.now().astimezone().utcoffset())
        self.assertEqual(local_day(now()), today())

    def test_old_utc_stamps_are_read_as_local_days(self):
        # Monday 00:30 in Berlin (summer time) was stored as Sunday 22:30 UTC.
        self.assertEqual(local_day("2026-10-18T22:30:00+00:00"), "2026-10-19")
        self.assertEqual(local_day("2026-10-18T22:30:00Z"), "2026-10-19")
        # Winter time: one hour, not two.
        self.assertEqual(local_day("2026-11-01T23:30:00+00:00"), "2026-11-02")
        self.assertEqual(local_day("2026-11-01T22:30:00+00:00"), "2026-11-01")

    def test_naive_and_missing_stamps(self):
        self.assertEqual(local_day("2026-10-18T23:59:00"), "2026-10-18")  # already local
        self.assertEqual(local_day("2026-10-18"), "2026-10-18")
        self.assertEqual(local_day(""), "")
        self.assertEqual(local_day(None), "")

    def test_week_boundary_in_local_time(self):
        monday = date(2026, 10, 19)
        jobs = [
            # Monday 00:30 Berlin, stored as UTC by an older version: this week.
            {"status": "applied", "status_updated_at": "2026-10-18T22:30:00+00:00", "closed": 0},
            # Same moment, stored the new way: this week.
            {"status": "applied", "status_updated_at": "2026-10-19T00:30:00+02:00", "closed": 0},
            # Sunday 23:30 Berlin: last week, in either format.
            {"status": "applied", "status_updated_at": "2026-10-18T21:30:00+00:00", "closed": 0},
            {"status": "applied", "status_updated_at": "2026-10-18T23:30:00+02:00", "closed": 0},
        ]
        week = weekly_summary(jobs, today=monday)[0]
        self.assertEqual(week["weekOf"], "2026-10-19")
        self.assertEqual(week["applied"], 2)

    def test_database_writes_local_stamps(self):
        with tempfile.TemporaryDirectory() as d:
            db = DB(Path(d) / "t.db")
            db.log_run(today(), found=1)
            row = db.conn.execute("SELECT finished_at FROM run_log").fetchone()[0]
            self.assertIsNotNone(datetime.fromisoformat(row).tzinfo)
            self.assertEqual(local_day(row), today())
            db.conn.close()


if __name__ == "__main__":
    unittest.main()
