"""A company reposting the same title after the repost window must come back as a new job."""
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from stellenpilot import pipeline
from stellenpilot.db import DB
from stellenpilot.text import dedupe_key


def _job(i: str, title="Werkstudent Data Engineering (m/w/d)", company="Zalando SE"):
    return {"id": i, "source": "Test", "title": title, "company": company, "location": "Essen",
            "remote": False, "url": "", "posted_at": "", "description": "Python SQL"}


class _Settings(dict):
    def __getitem__(self, k):
        return dict.__getitem__(self, k)


def _settings(days=45):
    return _Settings({"sources": {"arbeitnow": True}, "watch": {},
                      "search": {"exclude_title_words": [], "country": "de", "repost_after_days": days}})


class RepostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DB(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.db.conn.close()
        self.tmp.cleanup()

    def _old(self, days_ago: int, status="applied"):
        j = _job("old-1")
        self.db.insert_job({**j, "dedupe_key": dedupe_key(j["company"], j["title"]), "status": status,
                            "found_at": (date.today() - timedelta(days=days_ago)).isoformat()})

    def _collect(self, settings, found):
        with mock.patch.object(pipeline.sources.REGISTRY["arbeitnow"], "fetch", return_value=found):
            return pipeline.collect(settings, self.db)

    def test_recent_duplicate_is_still_dropped(self):
        self._old(10)
        new, _ = self._collect(_settings(), [_job("new-1", company="Zalando")])
        self.assertEqual(new, [])

    def test_repost_after_window_comes_back_with_a_note(self):
        self._old(120, status="rejected")
        new, _ = self._collect(_settings(), [_job("new-1", company="Zalando")])
        self.assertEqual([j["id"] for j in new], ["new-1"])
        self.assertIn("Posted again", new[0]["status_note"])
        self.assertIn("rejected", new[0]["status_note"])

    def test_zero_days_keeps_the_old_forever_rule(self):
        self._old(400)
        new, _ = self._collect(_settings(days=0), [_job("new-1")])
        self.assertEqual(new, [])

    def test_same_run_duplicates_across_sources_are_dropped(self):
        new, _ = self._collect(_settings(), [_job("a"), _job("b", company="Zalando")])
        self.assertEqual([j["id"] for j in new], ["a"])

    def test_same_posting_id_is_never_added_twice(self):
        self._old(400)
        new, _ = self._collect(_settings(), [_job("old-1")])
        self.assertEqual(new, [])

    def test_bad_setting_falls_back_to_default(self):
        self.assertIsNotNone(pipeline.repost_since(_settings(days="soon")))


if __name__ == "__main__":
    unittest.main()
