import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from stellenpilot import schedule


class FakeSettings:
    def __init__(self, enabled, time):
        self.cfg = {"schedule": {"enabled": enabled, "time": time}}

    def __getitem__(self, k):
        return self.cfg[k]


class ScheduleTest(unittest.TestCase):
    def test_missed_today(self):
        s = FakeSettings(True, "08:45")
        nine = datetime(2026, 10, 12, 9, 20)
        self.assertTrue(schedule.missed_today(s, "2026-10-11", nine))
        self.assertFalse(schedule.missed_today(s, "2026-10-12", nine))           # already ran today
        self.assertFalse(schedule.missed_today(s, None, datetime(2026, 10, 12, 9, 0)))  # within grace time
        self.assertFalse(schedule.missed_today(FakeSettings(False, "08:45"), None, nine))

    @unittest.skipIf(sys.platform.startswith("win"), "crontab is for macOS and Linux")
    def test_crontab_add_and_remove_keeps_other_lines(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            store = d / "tab"
            store.write_text("0 1 * * * echo other\n")
            fake = d / "crontab"
            fake.write_text(f'#!/bin/sh\nif [ "$1" = "-l" ]; then cat "{store}"; else cat > "{store}"; fi\n')
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            home = d / "my hunt"
            home.mkdir()
            with mock.patch.dict(os.environ, {"PATH": f"{d}{os.pathsep}{os.environ['PATH']}"}), \
                 mock.patch.object(schedule, "in_docker", return_value=False):
                schedule.enable(home, "7:05")
                schedule.enable(home, "08:30")  # changing the time replaces the line
                tab = store.read_text()
                self.assertIn("echo other", tab)
                self.assertEqual(tab.count(schedule.MARK), 1)
                self.assertIn("30 8 * * *", tab)
                self.assertIn("'" + str(home.resolve()) + "'", tab)  # path with a space is quoted
                self.assertTrue(schedule.is_enabled(home))
                schedule.disable(home)
                self.assertEqual(store.read_text().strip(), "0 1 * * * echo other")
                self.assertFalse(schedule.is_enabled(home))

    def test_windows_xml_escapes_path(self):
        xml = schedule._windows_xml(Path("C:/a & b/jobhunt-daily.cmd"), 8, 5)
        self.assertIn("a &amp; b", xml)
        self.assertIn("T08:05:00", xml)
        self.assertIn("<StartWhenAvailable>true</StartWhenAvailable>", xml)


if __name__ == "__main__":
    unittest.main()
