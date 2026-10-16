"""TheirStack parser and query (issue #21). The sample follows the job object in TheirStack's docs:
https://theirstack.com/en/docs/api-reference/jobs/search_jobs_v1 . No network and no key needed."""
import unittest
from unittest import mock

from stellenpilot.sources import theirstack

LOCAL = {"data": [
    {"id": 101, "job_title": "Werkstudent Data Engineering", "company_object": {"id": "c1", "name": "Nordlicht Energy GmbH"},
     "short_location": "Essen, NW", "location": "Essen", "remote": False,
     "final_url": "https://careers.nordlicht.example/jobs/101", "url": "https://board.example/101",
     "description": "<p>You will build <b>Python</b> &amp; SQL pipelines.</p><ul><li>Airflow</li></ul>",
     "date_posted": "2026-10-14", "employment_statuses": ["part_time"]},
    # Only the deprecated top level name and no final_url: the fallbacks are used.
    {"id": 102, "job_title": "Data Analyst Teilzeit", "company": "Rhein Mobility AG", "company_object": {},
     "location": "Düsseldorf", "url": "https://board.example/102", "description": None,
     "date_posted": "2026-10-13T09:30:00Z", "employment_statuses": ["full_time"]},
]}
REMOTE = {"data": [
    {"id": 201, "job_title": "Junior Data Engineer", "company_object": {"id": "c3", "name": "Spree Insights"},
     "company": "Old Name Ltd", "short_location": "Berlin", "remote": True, "url": "https://board.example/201",
     "description": "Remote role", "date_posted": "2026-10-12", "employment_statuses": ["part_time"]},
]}


class FakeSettings:
    def __init__(self, key="k-123", include_remote=True, budget=6, **options):
        self._key = key
        self.cfg = {
            "search": {"keywords": ["Werkstudent Data", "Data Engineer"], "country": "de", "max_age_days": 7,
                       "include_remote": include_remote},
            "sources": {"limits": {"theirstack_jobs": budget}, "theirstack_options": options},
        }

    def __getitem__(self, k):
        return self.cfg[k]

    def secret(self, name):
        return self._key if name == "THEIRSTACK_API_KEY" else ""


class TheirStackTests(unittest.TestCase):
    def fetch(self, settings, *pages):
        with mock.patch.object(theirstack, "request_json", side_effect=list(pages)) as req:
            return theirstack.fetch(settings), req

    def test_parses_documented_fields(self):
        jobs, _ = self.fetch(FakeSettings(), LOCAL, REMOTE)
        self.assertEqual([j["id"] for j in jobs], ["ts-101", "ts-102", "ts-201"])
        a, b, c = jobs
        self.assertEqual(a["company"], "Nordlicht Energy GmbH")
        self.assertEqual(a["url"], "https://careers.nordlicht.example/jobs/101")  # career page over the board
        self.assertEqual(a["location"], "Essen, NW")
        self.assertEqual(a["job_type"], "Werkstudent")
        self.assertEqual(a["description"], "You will build Python & SQL pipelines.\nAirflow")
        self.assertEqual(a["posted_at"], "2026-10-14")
        self.assertEqual((a["source"], a["remote"]), ("TheirStack", False))

    def test_fallbacks_for_missing_fields(self):
        _, b, _ = self.fetch(FakeSettings(), LOCAL, REMOTE)[0]
        self.assertEqual(b["company"], "Rhein Mobility AG")  # deprecated field, only when company_object has no name
        self.assertEqual(b["url"], "https://board.example/102")
        self.assertEqual(b["location"], "Düsseldorf")
        self.assertEqual(b["description"], "")
        self.assertEqual(b["posted_at"], "2026-10-13")
        self.assertEqual(b["job_type"], "Part time")  # from the title

    def test_company_object_wins_over_deprecated_name(self):
        c = self.fetch(FakeSettings(), LOCAL, REMOTE)[0][2]
        self.assertEqual(c["company"], "Spree Insights")
        self.assertEqual(c["location"], "Remote, Berlin")
        self.assertEqual(c["job_type"], "Part time")  # from employment_statuses when the title says nothing

    def test_query_spends_the_budget_and_sends_the_key(self):
        _, req = self.fetch(FakeSettings(budget=6, location_ids=[2928810]), LOCAL, REMOTE)
        (url1, k1), (url2, k2) = [(c.args[0], c.kwargs) for c in req.call_args_list]
        self.assertEqual(url1, theirstack.URL)
        self.assertEqual(k1["headers"], {"Authorization": "Bearer k-123"})
        local, remote = k1["body"], k2["body"]
        self.assertEqual((local["limit"], remote["limit"]), (4, 2))  # 6 credits: 4 local, 2 remote
        self.assertEqual(local["job_location_or"], [{"id": 2928810}])
        self.assertEqual(remote["workplace_types_or"], ["remote"])
        self.assertEqual(local["job_country_code_or"], ["DE"])
        self.assertEqual(local["posted_at_max_age_days"], 7)
        self.assertEqual(local["job_title_pattern_or"], ["werkstudent.*data", "data.*werkstudent", "data.*engineer", "engineer.*data"])
        self.assertIn("job_description_pattern_and", local)  # English ads only, by default

    def test_no_remote_query_and_all_languages(self):
        _, req = self.fetch(FakeSettings(include_remote=False, english_only=False), LOCAL)
        self.assertEqual(req.call_count, 1)
        body = req.call_args.kwargs["body"]
        self.assertEqual(body["limit"], 6)
        self.assertNotIn("job_description_pattern_and", body)

    def test_missing_key_is_explained_without_a_request(self):
        with mock.patch.object(theirstack, "request_json") as req:
            with self.assertRaisesRegex(RuntimeError, "THEIRSTACK_API_KEY"):
                theirstack.fetch(FakeSettings(key=""))
        req.assert_not_called()


if __name__ == "__main__":
    unittest.main()
