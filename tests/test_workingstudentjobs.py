import unittest
from unittest import mock

from stellenpilot.http import HttpError
from stellenpilot.sources import workingstudentjobs as wsj


def settings(cities=("Essen",)):
    return {"search": {"keywords": ["Werkstudent Data"], "city": cities[0], "nearby_cities": list(cities[1:]),
                       "max_age_days": 3},
            "sources": {"limits": {}}}


def job(i, title="Werkstudent Data Engineering", company=True):
    return {"id": i, "title": title, "url": f"https://w/jobs/{i}", "apply_url": f"https://w/apply/{i}?ref=stellenpilot",
            "company": {"name": "ACME"} if company else None, "location": {"city": "Essen"},
            "types": ["working_student"], "working_mode": "remote", "skills": ["SQL", "Python"],
            "languages": {"german": "required"}, "posted_at": "2026-10-19T10:00:00Z"}


class WorkingStudentJobsTest(unittest.TestCase):
    def test_pages_filters_and_unknown_city(self):
        calls = []

        def fake(url, params=None, **kw):
            calls.append((url, params))
            if params and params["city"] == "atlantis":
                raise HttpError(400, "unknown_city")
            if params:  # first page of essen
                return {"data": [job("a"), job("b", "Koch"), job("c", company=False)], "links": {"next": "https://w/next"}}
            return {"data": [job("a"), job("d")], "links": {"next": None}}

        with mock.patch.object(wsj, "request_json", side_effect=fake):
            jobs = wsj.fetch(settings(("Essen", "Atlantis")))
        self.assertEqual([j["id"] for j in jobs], ["wsj-a", "wsj-c", "wsj-d"])
        self.assertEqual(calls[0][1]["city"], "essen")
        self.assertIn("since", calls[0][1])
        self.assertEqual(calls[1], ("https://w/next", None))
        self.assertEqual(jobs[1]["company"], "")
        self.assertEqual(jobs[0]["url"], "https://w/apply/a?ref=stellenpilot")
        self.assertEqual(jobs[0]["job_type"], "Werkstudent")
        self.assertTrue(jobs[0]["remote"])
        self.assertIn("German: required", jobs[0]["description"])
        self.assertEqual(wsj.PROBLEMS, ["city 'atlantis' is not known to workingstudentjobs.de"])


if __name__ == "__main__":
    unittest.main()
