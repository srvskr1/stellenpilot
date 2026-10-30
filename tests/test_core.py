"""Offline tests. Run with: python -m unittest discover -s tests"""
import json
import sqlite3
import tempfile
import tomllib
import unittest
import urllib.request
from importlib import resources
from pathlib import Path
from unittest import mock

from stellenpilot import sources
from stellenpilot.config import Settings
from stellenpilot.db import DB
from stellenpilot.score import keyword_score, llm_score, score_job
from stellenpilot.tailor import _valid_plan, make_plan, tailor_job, unsupported_claims
from stellenpilot.text import dedupe_key, requires_fluent_german, strip_html

PROFILE = tomllib.loads(resources.files("stellenpilot").joinpath("examples/profile.example.toml").read_text(encoding="utf-8"))
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

    def test_the_matched_skills_are_kept_for_the_dashboard(self):
        r = keyword_score(JOB, PROFILE)
        self.assertIn("Python", r["skills"])
        self.assertIn("SQL", r["skills"])
        self.assertNotIn("Snowflake", r["skills"])
        # The tools of the ad that the profile does not have stay out of the matched list.
        job = {**JOB, "description": JOB["description"] + " Snowflake and Kafka experience."}
        self.assertNotIn("Snowflake", keyword_score(job, PROFILE)["skills"])

    def test_the_ai_path_also_keeps_the_matched_skills(self):
        llm = mock.Mock(max_chars=4000)
        llm.complete_json.return_value = {"match": 70, "fit": "Possible", "why": "ok", "gaps": "Asks for dbt.",
                                          "gap_tags": ["dbt"]}
        r = llm_score(llm, JOB, PROFILE)
        self.assertIn("Python", r["skills"])

    def test_the_database_keeps_the_matched_skills(self):
        with tempfile.TemporaryDirectory() as d:
            db = DB(Path(d) / "t.db")
            db.insert_job({**JOB, "skills": ["Python", "SQL"], "gap_tags": ["dbt"]})
            row = db.jobs()[0]
            self.assertEqual(row["skills"], ["Python", "SQL"])
            self.assertEqual(row["gap_tags"], ["dbt"])
            db.conn.close()

    def test_an_old_database_gains_the_column(self):
        from stellenpilot.db import SCHEMA
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "old.db"
            conn = sqlite3.connect(path)
            conn.executescript(SCHEMA.replace("  skills TEXT NOT NULL DEFAULT '[]',\n", ""))
            conn.execute("INSERT INTO jobs (id, source, title, found_at, match) "
                         "VALUES ('old-1', 'Test', 'Old job', '2026-10-01', 50)")
            conn.commit()
            conn.close()
            db = DB(path)
            self.assertIn("skills", {r[1] for r in db.conn.execute("PRAGMA table_info(jobs)")})
            self.assertEqual(db.jobs()[0]["skills"], [])  # an old row has no skills yet
            db.conn.close()


class TruthGuardTests(unittest.TestCase):
    def test_rejects_invented_numbers_and_tools(self):
        self.assertIn("40%", unsupported_claims("I cut costs by 40% using Snowflake.", PROFILE))
        self.assertIn("Snowflake", unsupported_claims("I cut costs using Snowflake.", PROFILE))

    def test_allows_profile_facts_and_learning_mentions(self):
        self.assertEqual(unsupported_claims("I built Python and SQL pipelines on AWS S3 and Glue.", PROFILE), [])
        snow_job = {**JOB, "description": JOB["description"] + " Snowflake is a plus."}
        self.assertEqual(unsupported_claims("I am eager to learn Snowflake on the job.", PROFILE, snow_job), [])
        # learning words elsewhere do not unlock a claim of real use
        self.assertIn("Snowflake", unsupported_claims("I am eager to learn. I ran Snowflake in production.", PROFILE, snow_job))
        self.assertIn("Snowflake", unsupported_claims("I learned Snowflake while building warehouses.", PROFILE, snow_job))

    def test_language_level_claims_are_checked(self):
        de_job = {**JOB, "description": "Kafka, Snowflake, Deutschkenntnisse"}
        self.assertTrue(unsupported_claims("Meine Deutschkenntnisse sind fließend.", PROFILE, de_job))
        self.assertTrue(unsupported_claims("I speak German at C1 level.", PROFILE, de_job))
        self.assertEqual(unsupported_claims("My German is basic (A2) and I am improving it.", PROFILE, de_job), [])

    def test_loose_learning_words_do_not_unlock_claims(self):
        de_job = {**JOB, "description": "Kafka, Snowflake"}
        self.assertIn("Kafka", unsupported_claims("Dabei konnte ich meine Kenntnisse in Kafka vertiefen.", PROFILE, de_job))
        self.assertIn("Kafka", unsupported_claims("I used Kafka for machine learning features.", PROFILE, de_job))
        self.assertEqual(unsupported_claims("In Kafka arbeite ich mich gerade ein.", PROFILE, de_job), [])
        self.assertEqual(unsupported_claims("Mit Snowflake habe ich noch nicht gearbeitet, lerne es aber gern.", PROFILE, de_job), [])

    def test_learning_words_never_cover_a_claim_of_use(self):
        # Audit finding B1: a learning word used to unlock any tool the ad named.
        snow_job = {**JOB, "description": JOB["description"] + " You use Snowflake daily."}
        self.assertIn("Snowflake", unsupported_claims("I used Snowflake daily at my last job, a great learning experience.", PROFILE, snow_job))
        self.assertIn("Kafka", unsupported_claims("I built pipelines in Kafka while learning.", PROFILE, snow_job))
        self.assertIn("Snowflake", unsupported_claims("I have not used dbt yet, but I built Snowflake pipelines.", PROFILE, snow_job))
        self.assertIn("Snowflake", unsupported_claims("I have used Snowflake a lot.", PROFILE, snow_job))

    def test_currently_learning_only_for_the_learning_list(self):
        snow_job = {**JOB, "description": JOB["description"] + " Snowflake and Kafka."}
        self.assertIn("Snowflake", unsupported_claims("I am learning Snowflake.", PROFILE, snow_job))
        self.assertIn("Snowflake", unsupported_claims("In Snowflake arbeite ich mich gerade ein.", PROFILE, snow_job))
        self.assertEqual(unsupported_claims("I am currently learning Kafka.", PROFILE, snow_job), [])
        self.assertEqual(unsupported_claims("I have not worked with Snowflake yet and would like to learn it.", PROFILE, snow_job), [])
        self.assertEqual(unsupported_claims("I have no experience with Snowflake yet.", PROFILE, snow_job), [])
        # a tool the ad does not name cannot be dropped in, even as a gap
        self.assertIn("Snowflake", unsupported_claims("I have not used Snowflake yet.", PROFILE, JOB))

    def test_template_letters_pass_their_own_guard(self):
        from stellenpilot.tailor import keyword_plan, template_letter, template_letter_de
        job = {**JOB, "description": JOB["description"] + " Snowflake and Kafka."}
        plan = keyword_plan(job, PROFILE)
        for letter in (template_letter(job, plan), template_letter_de(job, plan)):
            self.assertEqual(unsupported_claims(letter, PROFILE, job), [], letter)

    def test_learning_skills_are_not_experience(self):
        self.assertIn("dbt", unsupported_claims("I built dbt models in production.", PROFILE, JOB))
        from stellenpilot.tailor import coverage
        cov = coverage(JOB, PROFILE)
        self.assertIn("dbt", cov["learning"])
        self.assertNotIn("dbt", cov["covered"])

    def test_common_words_are_not_tools(self):
        self.assertEqual(unsupported_claims("I excel at clear reporting and spark ideas.", PROFILE), [])
        n26 = {**JOB, "company": "N26"}
        self.assertEqual(unsupported_claims("I would love to join N26.", PROFILE, n26), [])

    def test_llm_covered_list_is_ignored(self):
        fake = mock.Mock(enabled=True, max_chars=6000)
        fake.complete_json.return_value = {"summary": "", "covered": ["Kubernetes", "10 years of leadership"]}
        plan = make_plan(JOB, PROFILE, fake)
        self.assertNotIn("Kubernetes", plan["covered"])
        self.assertNotIn("10 years of leadership", plan["covered"])

    def test_plan_indexes_are_clamped(self):
        plan = _valid_plan({"headline_index": 99, "experience": [[7, 0, 0]], "projects": [5, -1]}, PROFILE)
        self.assertEqual(plan["headline_index"], 0)
        self.assertEqual(plan["experience"][0], [0])
        self.assertEqual(plan["projects"], list(range(len(PROFILE["projects"]))))

    def test_malformed_llm_plan_is_survived(self):
        plan = _valid_plan({"headline_index": "1", "skill_groups": [["Cloud"]], "experience": [[[0], {"a": 1}, 0]],
                            "projects": [{"i": 0}, [1]], "summary": ["x"]}, PROFILE)
        self.assertEqual(plan["experience"][0], [0])
        self.assertEqual(plan["summary"], "")

    def test_llm_summary_with_fake_fact_falls_back(self):
        fake = mock.Mock(enabled=True, max_chars=6000)
        fake.complete_json.return_value = {"summary": "I led a team of 12 and used Snowflake daily."}
        plan = make_plan(JOB, PROFILE, fake)
        self.assertEqual(plan["summary"], PROFILE["person"]["summary"])
        self.assertIn("guard", plan)

    def test_tailor_writes_documents_with_verbatim_bullets(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            res = tailor_job({**JOB, "match": 80}, PROFILE, Path(d), llm=None, make_pdf=False)
            from docx import Document
            text = "\n".join(p.text for p in Document(res["files"][0]).paragraphs)
            for b in PROFILE["experience"][0]["bullets"]:
                self.assertIn(b, text)


class SparseProfileTests(unittest.TestCase):
    def test_minimal_profile_still_builds_documents(self):
        tiny = {"person": {}, "experience": [{"bullets": ["Did a thing."]}], "education": [{"degree": "BSc"}]}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            res = tailor_job({**JOB, "match": 80}, tiny, Path(d), llm=None, make_pdf=False)
            self.assertEqual(len(res["files"]), 3)

    def test_two_roles_at_one_company_get_separate_folders(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            a = tailor_job({**JOB, "title": "Data Engineer"}, PROFILE, Path(d), make_pdf=False)
            b = tailor_job({**JOB, "title": "BI Analyst"}, PROFILE, Path(d), make_pdf=False)
            self.assertNotEqual(a["folder"], b["folder"])


class GmailLogicTests(unittest.TestCase):
    def test_classifier_ignores_alerts_and_plurals(self):
        from stellenpilot.gmail_sync import ALERT, classify
        self.assertIsNone(classify("30 new job offers for you"))
        self.assertTrue(ALERT.search("LinkedIn Job Alerts"))
        self.assertEqual(classify("Unfortunately, we decided not to move forward"), "rejected")

    def test_company_matching_is_strict(self):
        from stellenpilot.gmail_sync import _company_matches
        from stellenpilot.text import _norm
        self.assertFalse(_company_matches("Data Solutions GmbH", _norm("Siemens: news from the big data team"), "siemens.com"))
        self.assertTrue(_company_matches("Siemens AG", _norm("Your application at Siemens"), "x.com"))
        self.assertTrue(_company_matches("Nordlicht Energy GmbH", _norm("Thank you"), "jobs.nordlicht.de"))


class DbTests(unittest.TestCase):
    def test_run_does_not_undo_a_manual_status(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            db = DB(Path(d) / "t.db")
            self.addCleanup(db.conn.close)  # before the folder is removed (Windows locks open files)
            db.insert_job({**JOB, "dedupe_key": "k"})
            db.set_status("t-1", "applied", source="manual")
            db.mark_ready("t-1", "/tmp/x", "note")
            j = db.job("t-1")
            self.assertEqual((j["status"], j["folder"]), ("applied", "/tmp/x"))

    def test_pipeline_never_overwrites_user_fields(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            db = DB(Path(d) / "t.db")
            self.addCleanup(db.conn.close)  # before the folder is removed (Windows locks open files)
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
        st.__getitem__ = lambda self, k: {"search": {"city": "Essen", "nearby_cities": [], "max_age_days": 3, "include_remote": True, "keywords": ["Werkstudent Data"]}, "sources": {"limits": {}}}[k]
        with mock.patch("stellenpilot.sources.arbeitnow.request_json", side_effect=[page, {"data": []}]):
            ids = [j["id"] for j in sources.arbeitnow.fetch(st)]
        self.assertEqual(ids, ["an-a", "an-c"])


class ServerTests(unittest.TestCase):
    def test_patch_requires_header_and_saves(self):
        from helpers import fetch, fetch_json, http_error, running
        from stellenpilot.server import make_handler
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            settings = Settings(Path(d))
            db = DB(settings.db_path)
            db.insert_job({**JOB, "dedupe_key": "k"})
            db.conn.close()
            with running(make_handler(settings)) as srv:
                body = json.dumps({"status": "applied"}).encode()
                req = urllib.request.Request(f"{srv.base}/api/jobs/t-1", data=body, method="PATCH")
                self.assertEqual(http_error(req)[0], 403)
                req = urllib.request.Request(f"{srv.base}/api/jobs/t-1", data=body, method="PATCH",
                                             headers={"X-Jobhunt": "1", "Content-Type": "application/json"})
                fetch(req)
                state = fetch_json(f"{srv.base}/api/state")
                self.assertEqual(state["jobs"][0]["status"], "applied")
                self.assertEqual(state["jobs"][0]["statusSource"], "manual")
                bad_host = urllib.request.Request(f"{srv.base}/api/state", headers={"Host": f"evil.example:{srv.port}"})
                self.assertEqual(http_error(bad_host)[0], 403)


if __name__ == "__main__":
    unittest.main()


class OfflineMessageTest(unittest.TestCase):
    def test_all_sources_offline_gives_one_clear_line(self):
        import socket, urllib.error
        from unittest import mock
        from stellenpilot import pipeline
        err = urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))
        st = mock.MagicMock()
        cfg = {"sources": {"arbeitsagentur": True, "arbeitnow": True}, "watch": {}, "search": {"exclude_title_words": [], "country": "de"}}
        st.__getitem__.side_effect = lambda k: cfg[k]
        db = mock.MagicMock(); db.job_ids.return_value = set(); db.dedupe_keys.return_value = set()
        with mock.patch.object(pipeline.sources.REGISTRY["arbeitsagentur"], "fetch", side_effect=err), \
             mock.patch.object(pipeline.sources.REGISTRY["arbeitnow"], "fetch", side_effect=err):
            new, problems = pipeline.collect(st, db)
        self.assertEqual(new, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("internet connection", problems[0])


class ParallelSourcesTest(unittest.TestCase):
    def test_sources_run_at_once_and_order_still_decides_duplicates(self):
        import time
        from stellenpilot import pipeline
        st = mock.MagicMock()
        cfg = {"sources": {"arbeitsagentur": True, "arbeitnow": True, "remotive": True}, "watch": {},
               "search": {"exclude_title_words": [], "country": "de"}}
        st.__getitem__.side_effect = lambda k: cfg[k]
        db = mock.MagicMock(); db.job_ids.return_value = set(); db.dedupe_keys.return_value = set()

        def slow(src, delay):
            def fetch(_):
                time.sleep(delay)
                return [{"id": src, "company": "Acme", "title": "Data Engineer", "source": src}]
            return fetch
        with mock.patch.object(pipeline.sources.REGISTRY["arbeitsagentur"], "fetch", slow("arbeitsagentur", 0.6)), \
             mock.patch.object(pipeline.sources.REGISTRY["arbeitnow"], "fetch", slow("arbeitnow", 0.1)), \
             mock.patch.object(pipeline.sources.REGISTRY["remotive"], "fetch", side_effect=RuntimeError("down")), \
             mock.patch.object(pipeline, "repost_since", return_value=None):
            start = time.monotonic()
            new, problems = pipeline.collect(st, db)
            took = time.monotonic() - start
        self.assertLess(took, 0.65)  # one after another would take 0.7
        self.assertEqual([j["id"] for j in new], ["arbeitsagentur"])  # ORDER wins, not the faster source
        self.assertEqual(len(problems), 1)
        self.assertIn("remotive", problems[0])
