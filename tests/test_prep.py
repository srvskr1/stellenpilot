"""Interview prep on any job, without AI too, and the checklist ticks."""
import json
import tempfile
import tomllib
import unittest
import urllib.request
from importlib import resources
from pathlib import Path

from stellenpilot.config import Settings
from stellenpilot.db import DB
from stellenpilot.pipeline import basic_prep, grade_answer, make_prep, stronger_answer

PROFILE = tomllib.loads(resources.files("stellenpilot").joinpath("examples/profile.example.toml").read_text(encoding="utf-8"))
JOB = {"id": "p-1", "source": "Test", "title": "Data Engineer", "company": "Ruhr Energie", "location": "Essen",
       "url": "https://example.com", "description": "Ruhr Energie runs the grid in the Ruhr area. You build pipelines "
       "with Python, SQL and Kafka. Gehalt: 55.000 bis 65.000 € brutto im Jahr.", "dedupe_key": "k"}


class NoAI:
    enabled = False


class FakeLLM:
    """Returns whatever the test sets in `reply`, so grading logic is checked without a model."""
    enabled = True
    max_chars = 4000

    def __init__(self, reply):
        self.reply = reply

    def complete_json(self, system, user, max_tokens=0):
        return self.reply


class MockInterviewTests(unittest.TestCase):
    def test_grade_clamps_rating_and_trims_points(self):
        g = grade_answer(JOB, PROFILE, "Tell us about a pipeline.", "I built one with Python.",
                         FakeLLM({"rating": 9, "worked": ["a", "b", "c"], "improve": ["x"]}))
        self.assertEqual(g["rating"], 2)            # 9 clamped into 0..2
        self.assertEqual(len(g["worked"]), 2)       # at most two points
        self.assertEqual(g["improve"], ["x"])

    def test_grade_defaults_to_good_on_junk(self):
        g = grade_answer(JOB, PROFILE, "q", "a", FakeLLM({"worked": None, "improve": None}))
        self.assertEqual((g["rating"], g["worked"], g["improve"]), (1, [], []))

    def test_stronger_drops_claims_not_in_the_cv(self):
        # The first sentence is grounded, the second claims a tool the profile does not have.
        text = stronger_answer(JOB, PROFILE, "q", "a",
                               FakeLLM({"stronger": "I built Python pipelines at work. I have shipped production Kafka clusters for years."}))
        self.assertIn("Python", text)
        self.assertNotIn("Kafka", text)

    def test_mock_route_needs_ai(self):
        from helpers import fetch_json, http_error, running
        from stellenpilot.server import make_handler
        hdr = {"X-Jobhunt": "1", "Content-Type": "application/json"}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            settings = Settings(Path(d))
            settings["llm"]["provider"] = "none"
            db = DB(settings.db_path)
            db.insert_job(JOB)
            db.conn.close()
            with running(make_handler(settings)) as srv:
                req = lambda body: urllib.request.Request(f"{srv.base}/api/mock/grade", data=json.dumps(body).encode(), method="POST", headers=hdr)
                self.assertEqual(http_error(req({"id": "p-1", "question": "q", "answer": ""}))[0], 400)   # empty answer
                self.assertEqual(http_error(req({"id": "p-1", "question": "q", "answer": "Something."}))[0], 400)  # no AI on
                # mock answers round-trip through the job the same way prep does
                patch = urllib.request.Request(f"{srv.base}/api/jobs/p-1", data=json.dumps({"mock": '{"answers":{"0":{"a":"hi","self":2}}}'}).encode(), method="PATCH", headers=hdr)
                urllib.request.urlopen(patch)
                saved = json.loads(fetch_json(f"{srv.base}/api/state")["jobs"][0]["mock"])
                self.assertEqual(saved["answers"]["0"], {"a": "hi", "self": 2})
                # invalid JSON in mock is refused
                bad = urllib.request.Request(f"{srv.base}/api/jobs/p-1", data=json.dumps({"mock": "{not json"}).encode(), method="PATCH", headers=hdr)
                self.assertEqual(http_error(bad)[0], 400)


class BasicPrepTests(unittest.TestCase):
    def test_built_from_the_ad_and_the_gaps(self):
        text = basic_prep(JOB, PROFILE)
        for head in ("## About Ruhr Energie", "## Likely questions", "## Your gaps and how to answer", "## Questions to ask them"):
            self.assertIn(head, text)
        self.assertIn("Kafka", text.split("## Your gaps")[1])
        self.assertIn("runs the grid", text)

    def test_make_prep_without_ai_never_calls_a_model(self):
        self.assertEqual(make_prep(JOB, PROFILE, NoAI()), basic_prep(JOB, PROFILE))


class RouteTests(unittest.TestCase):
    def test_prep_route_and_checklist(self):
        from helpers import fetch, fetch_json, http_error, running
        from stellenpilot.server import make_handler
        hdr = {"X-Jobhunt": "1", "Content-Type": "application/json"}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            settings = Settings(Path(d))
            settings["llm"]["provider"] = "none"
            db = DB(settings.db_path)
            db.insert_job(JOB)
            db.conn.close()
            with running(make_handler(settings)) as srv:
                fetch(urllib.request.Request(f"{srv.base}/api/prep/p-1", data=b"{}", method="POST", headers=hdr))
                patch = lambda v: urllib.request.Request(f"{srv.base}/api/jobs/p-1", data=json.dumps({"prepDone": v}).encode(),
                                                         method="PATCH", headers=hdr)
                fetch(patch("2,0,2"))
                self.assertEqual(http_error(patch("7"))[0], 400)
                job = fetch_json(f"{srv.base}/api/state")["jobs"][0]
                self.assertIn("## Likely questions", job["prep"])
                self.assertEqual(job["prepDone"], "0,2")
                self.assertEqual((job["pay"]["lo"], job["pay"]["hi"]), (55000, 65000))
                self.assertEqual(http_error(urllib.request.Request(f"{srv.base}/api/prep/nope", data=b"{}", method="POST", headers=hdr))[0], 404)


if __name__ == "__main__":
    unittest.main()
