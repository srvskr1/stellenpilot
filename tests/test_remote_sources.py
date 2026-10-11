import unittest
from datetime import date, timedelta
from unittest import mock

from stellenpilot.http import HttpError
from stellenpilot.sources import jobicy, remotive

TODAY = date.today().isoformat()
OLD = (date.today() - timedelta(days=30)).isoformat()


class S:
    def __init__(self, remote=True, country="de"):
        self.cfg = {"search": {"keywords": ["Data Engineer"], "country": country, "max_age_days": 3,
                               "include_remote": remote, "exclude_title_words": ["senior"]},
                    "sources": {"limits": {}}}

    def __getitem__(self, k):
        return self.cfg[k]


class RemotiveTest(unittest.TestCase):
    def feed(self):
        return {"jobs": [
            {"id": 1, "title": "Data Engineer", "candidate_required_location": "Europe", "publication_date": TODAY + "T10:00:00", "url": "https://remotive.com/x/1"},
            {"id": 2, "title": "Data Engineer", "candidate_required_location": "USA Only", "publication_date": TODAY},
            {"id": 3, "title": "Senior Data Engineer", "candidate_required_location": "Worldwide", "publication_date": TODAY},
            {"id": 4, "title": "Data Engineer", "candidate_required_location": "Germany", "publication_date": OLD},
            {"id": 5, "title": "Designer", "candidate_required_location": "Worldwide", "publication_date": TODAY},
        ]}

    def test_one_call_and_filters(self):
        with mock.patch.object(remotive, "request_json", return_value=self.feed()) as m:
            jobs = remotive.fetch(S())
        self.assertEqual(m.call_count, 1)
        self.assertEqual([j["id"] for j in jobs], ["rm-1"])
        self.assertTrue(jobs[0]["remote"])
        self.assertEqual(jobs[0]["source"], "Remotive")

    def test_skipped_without_remote(self):
        with mock.patch.object(remotive, "request_json") as m:
            self.assertEqual(remotive.fetch(S(remote=False)), [])
        m.assert_not_called()


class JobicyTest(unittest.TestCase):
    def page(self, ids, more=False):
        return {"jobs": [{"id": i, "jobTitle": "Data Engineer", "url": f"https://jobicy.com/jobs/{i}", "pubDate": TODAY} for i in ids],
                "hasMore": "True" if more else "False", "nextCursor": "c" if more else None}

    def test_regions_cursor_and_dedupe(self):
        calls = []

        def fake(url, params=None, **kw):
            calls.append(dict(params))
            if params["geo"] == "germany":
                return self.page([1, 2])
            return self.page([2, 3], more=True) if "cursor" not in params else self.page([4])
        with mock.patch.object(jobicy, "request_json", side_effect=fake), mock.patch.object(jobicy.time, "sleep"):
            jobs = jobicy.fetch(S())
        self.assertEqual([c["geo"] for c in calls], ["germany", "europe", "europe"])
        self.assertEqual(sorted(j["id"] for j in jobs), ["jc-1", "jc-2", "jc-3", "jc-4"])

    def test_block_keeps_what_it_has(self):
        def fake(url, params=None, **kw):
            if params["geo"] == "europe":
                raise HttpError(403, "Just a moment")
            return self.page([1])
        with mock.patch.object(jobicy, "request_json", side_effect=fake), mock.patch.object(jobicy.time, "sleep"):
            self.assertEqual([j["id"] for j in jobicy.fetch(S())], ["jc-1"])


if __name__ == "__main__":
    unittest.main()


class OrderTest(unittest.TestCase):
    def test_every_source_runs(self):
        from stellenpilot import pipeline, sources
        self.assertEqual(set(pipeline.ORDER), set(sources.REGISTRY))
