"""Offline tests. Run with: python -m unittest discover -s tests"""
import json
import tempfile
import threading
import tomllib
import unittest
import urllib.request
from importlib import resources
from pathlib import Path
from unittest import mock

from jobhunt import sources
from jobhunt.config import Settings
from jobhunt.db import DB
from jobhunt.score import keyword_score, score_job
from jobhunt.tailor import _valid_plan, make_plan, tailor_job, unsupported_claims
from jobhunt.text import dedupe_key, requires_fluent_german, strip_html

PROFILE = tomllib.loads(resources.files("jobhunt").joinpath("examples/profile.example.toml").read_text(encoding="utf-8"))
JOB = {"id": "t-1", "source": "Test", "title": "Working Student Data Engineering (m/w/d)", "company": "Test GmbH",
       "location": "Essen", "remote": False, "url": "https://example.com", "posted_at": "",
       "description": "You will build pipelines with Python, SQL, Airflow and dbt on AWS. Good English."}


class TextTests(unittest.TestCase):
    def test_dedupe_key_ignores_gender_tags_and_legal_form(self):
        self.assertEqual(dedupe_key("Test GmbH", "Data Engineer (m/w/d)"), dedupe_key("test", "Data Engineer (f/m/x)"))

    def test_fluent_german_detection(self):
        self.assertTrue(requires_fluent_german("Sehr gute Deutschkenntnisse in Wort und Schrift"))
        self.assertTrue(requires_fluent_german("Fluent German (C1) is required"))
        self.assertFalse(requires_fluent_german("German is a plus, English is our working language"))

    def test_strip_html(self):
        self.assertEqual(strip_html("<p>Hello&nbsp;<b>you</b></p><li>x</li>"), "Hello you\nx")


class ScoreTests(unittest.TestCase):
    def test_keyword_score_flags_gaps(self):
        r = keyword_score(JOB, PROFILE)
        job = {**JOB, "description": JOB["description"] + " Snowflake and Kafka experience."}
        r = keyword_score(job, PROFILE)
        self.assertIn("Snowflake", r["gap_tags"])
        self.assertGreater(r["match"], 50)

    def test_german_requirement_skips(self):
        job = {**JOB, "description": JOB["description"] + " Verhandlungssichere Deutschkenntnisse."}
        r = score_job(job, PROFILE)
        self.assertEqual(r["lang"], "German needed")
        self.assertEqual(r["status"], "skipped")


class TruthGuardTests(unittest.TestCase):
    def test_rejects_invented_numbers_and_tools(self):
        self.assertIn("40%", unsupported_claims("I cut costs by 40% using Snowflake.", PROFILE))
        self.assertIn("Snowflake", unsupported_claims("I cut costs using Snowflake.", PROFILE))

    def test_allows_profile_facts_and_learning_mentions(self):
        self.assertEqual(unsupported_claims("I built Python and SQL pipelines on AWS S3 and Glue.", PROFILE), [])
        self.assertEqual(unsupported_claims("I am eager to learn Snowflake on the job.", PROFILE), [])

    def test_plan_indexes_are_clamped(self):
        plan = _valid_plan({"headline_index": 99, "experience": [[7, 0, 0]], "projects": [5, -1]}, PROFILE)
        self.assertEqual(plan["headline_index"], 0)
        self.assertEqual(plan["experience"][0], [0])
        self.assertEqual(plan["projects"], list(range(len(PROFILE["projects"]))))

    def test_llm_summary_with_fake_fact_falls_back(self):
        fake = mock.Mock(enabled=True)
        fake.complete_json.return_value = {"summary": "I led a team of 12 and used Snowflake daily."}
        plan = make_plan(JOB, PROFILE, fake)
        self.assertEqual(plan["summary"], PROFILE["person"]["summary"])
        self.assertIn("guard", plan)

    def test_tailor_writes_documents_with_verbatim_bullets(self):
        with tempfile.TemporaryDirectory() as d:
            res = tailor_job({**JOB, "match": 80}, PROFILE, Path(d), llm=None, make_pdf=False)
            from docx import Document
            text = "\n".join(p.text for p in Document(res["files"][0]).paragraphs)
            for b in PROFILE["experience"][0]["bullets"]:
                self.assertIn(b, text)


class DbTests(unittest.TestCase):
    def test_pipeline_never_overwrites_user_fields(self):
        with tempfile.TemporaryDirectory() as d:
            db = DB(Path(d) / "t.db")
            db.insert_job({**JOB, "dedupe_key": "k"})
            db.update_job("t-1", {"notes": "mine", "rating": 1}, by_user=True)
            db.update_job("t-1", {"notes": "overwritten", "rating": -1, "match": 50})
            j = db.job("t-1")
            self.assertEqual((j["notes"], j["rating"], j["match"]), ("mine", 1, 50))


class SourceTests(unittest.TestCase):
    def test_arbeitnow_filters_by_place_and_title(self):
        import time
        now = int(time.time())
        page = {"data": [
            {"slug": "a", "title": "Werkstudent Data Engineering", "company_name": "A", "location": "Essen", "remote": False, "created_at": now, "description": "<p>x</p>", "job_types": ["working student"], "url": "u"},
            {"slug": "b", "title": "Werkstudent Data", "company_name": "B", "location": "Munich", "remote": False, "created_at": now, "description": "", "job_types": [], "url": "u"},
            {"slug": "c", "title": "Werkstudent Data", "company_name": "C", "location": "Munich", "remote": True, "created_at": now, "description": "", "job_types": [], "url": "u"},
        ]}
        st = mock.Mock()
        st.__getitem__ = lambda self, k: {"search": {"city": "Essen", "nearby_cities": [], "max_age_days": 3, "include_remote": True, "keywords": ["Werkstudent Data"]}}[k]
        with mock.patch("jobhunt.sources.arbeitnow.request_json", side_effect=[page, {"data": []}]):
            ids = [j["id"] for j in sources.arbeitnow.fetch(st)]
        self.assertEqual(ids, ["an-a", "an-c"])


class ServerTests(unittest.TestCase):
    def test_patch_requires_header_and_saves(self):
        from http.server import ThreadingHTTPServer
        from jobhunt.server import make_handler
        with tempfile.TemporaryDirectory() as d:
            settings = Settings(Path(d))
            DB(settings.db_path).insert_job({**JOB, "dedupe_key": "k"})
            srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(settings))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            body = json.dumps({"status": "applied"}).encode()
            req = urllib.request.Request(f"{base}/api/jobs/t-1", data=body, method="PATCH")
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req)
            self.assertEqual(e.exception.code, 403)
            req = urllib.request.Request(f"{base}/api/jobs/t-1", data=body, method="PATCH",
                                         headers={"X-Jobhunt": "1", "Content-Type": "application/json"})
            urllib.request.urlopen(req)
            state = json.load(urllib.request.urlopen(f"{base}/api/state"))
            self.assertEqual(state["jobs"][0]["status"], "applied")
            self.assertEqual(state["jobs"][0]["statusSource"], "manual")
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
