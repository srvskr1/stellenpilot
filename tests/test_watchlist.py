"""Watchlist feeds, parsed from small recorded samples (no network)."""
import json
import unittest
from unittest import mock

from jobhunt.sources import watchlist as wl

GH = {"jobs": [{"id": 1, "title": "Working Student - Data & Insights", "company_name": "trivago",
                "location": {"name": "Düsseldorf"}, "absolute_url": "https://x/1", "first_published": "2026-10-01T10:00:00+02:00",
                "content": "&lt;p&gt;You will use SQL&lt;/p&gt;"}]}
LEVER = [{"id": "a1", "text": "Data Engineer", "categories": {"location": "Berlin"}, "workplaceType": "hybrid",
          "hostedUrl": "https://jobs.lever.co/x/a1", "descriptionPlain": "Python", "lists": [{"text": "You have", "content": "<li>SQL</li>"}],
          "createdAt": 1791000000000}]
ASHBY = {"jobs": [{"id": "z", "title": "Data Analyst", "location": "Remote", "isRemote": True, "isListed": True,
                   "jobUrl": "https://jobs.ashbyhq.com/x/z", "descriptionPlain": "dbt", "publishedAt": "2026-10-02T00:00:00Z"}]}
PERSONIO = """<?xml version="1.0" encoding="UTF-8"?><workzag-jobs><position><id>42</id><subcompany>Acme GmbH</subcompany>
<office>Essen</office><name>Werkstudent Data</name><createdAt>2026-10-03T08:00:00+00:00</createdAt>
<jobDescriptions><jobDescription><name>Tasks</name><value><![CDATA[<p>SQL reports</p>]]></value></jobDescription></jobDescriptions>
</position></workzag-jobs>"""


class WatchlistTests(unittest.TestCase):
    def test_parse_careers_urls(self):
        cases = {
            "https://job-boards.greenhouse.io/trivago/jobs/8675630002": "greenhouse:trivago",
            "https://boards.greenhouse.io/embed/job_board?for=n26": "greenhouse:n26",
            "https://jobs.lever.co/spotify/abc": "lever:spotify",
            "https://jobs.eu.lever.co/acme": "lever:acme",
            "https://jobs.ashbyhq.com/deepl/123": "ashby:deepl",
            "https://hornetsecurity.jobs.personio.de/job/1": "personio:hornetsecurity",
            "https://jobs.smartrecruiters.com/BoschGroup/7443": "smartrecruiters:BoschGroup",
            "https://www.linkedin.com/jobs/view/1": None,
        }
        for url, entry in cases.items():
            self.assertEqual(wl.parse_careers_url(url), entry, url)

    def test_greenhouse_unescapes_content(self):
        with mock.patch.object(wl, "request_json", return_value=GH):
            j = wl.greenhouse("trivago")[0]
        self.assertEqual(j["description"], "You will use SQL")
        self.assertEqual(j["posted_at"], "2026-10-01")

    def test_lever_epoch_ms_and_lists(self):
        with mock.patch.object(wl, "request_json", return_value=LEVER):
            j = wl.lever("x")[0]
        self.assertIn("SQL", j["description"])
        self.assertTrue(j["posted_at"].startswith("2026"))

    def test_lever_falls_back_to_eu_host(self):
        from jobhunt.http import HttpError
        with mock.patch.object(wl, "request_json", side_effect=[HttpError(404, "nf"), LEVER]) as m:
            wl.lever("x")
        self.assertIn("api.eu.lever.co", m.call_args_list[1].args[0])

    def test_ashby_remote(self):
        with mock.patch.object(wl, "request_json", return_value=ASHBY):
            self.assertTrue(wl.ashby("x")[0]["remote"])

    def test_personio_xml(self):
        with mock.patch.object(wl, "_text", return_value=PERSONIO):
            j = wl.personio("acme")[0]
        self.assertEqual((j["title"], j["company"], j["location"]), ("Werkstudent Data", "Acme GmbH", "Essen"))
        self.assertIn("SQL reports", j["description"])

    def test_title_rules_need_all_words(self):
        rules = [["data", "engineer"], ["data"]]
        self.assertTrue(wl.title_matches("Backend Engineer - Data Platform", rules))
        self.assertFalse(wl.title_matches("Android Engineer", [["data", "engineer"]]))

    def test_bad_entry_is_explained(self):
        with self.assertRaises(RuntimeError):
            wl.fetch_company("workday:acme")


if __name__ == "__main__":
    unittest.main()
