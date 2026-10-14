"""A CV imported without an AI must still be usable, and an empty profile must never fail silently."""
import json
import os
import stat
import tempfile
import threading
import tomllib
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from stellenpilot import importer
from stellenpilot.cli import setup_checks
from stellenpilot.config import Settings
from stellenpilot.score import keyword_score, profile_gaps

CV = """SOURAV SARKER
Data Engineer | Cloud Data Pipelines
Essen, Germany | sourav@example.com | +49 157 0000 0000 | github.com/srvskr1
Technical Skills
Cloud: AWS (S3, Glue, Athena), Azure Data Factory, Databricks
Programming: Python (Pandas, NumPy, PySpark), SQL
Currently Learning: dbt, Apache Kafka, Terraform
Coursework: Advanced Machine Learning, Deep Learning
Weather ETL project
Extending the load stage to Azure Blob Storage, with GitHub Actions CI/CD and Terraform provisioning planned.
Built dashboards in Power BI and Tableau.
Professional Experience
Junior Data Analyst, Techmak Technology   2020 to 2023
"""

EMPTY = {"person": {"name": "Sourav", "languages": ["German (A2)"]}, "skills": {}, "experience": [], "projects": []}


class RuleSkillsTests(unittest.TestCase):
    def test_finds_used_tools_and_keeps_learning_apart(self):
        s = importer.rule_skills(CV)
        for tool in ("Python", "SQL", "AWS", "S3", "Glue", "Athena", "Azure Data Factory", "Databricks", "PySpark",
                     "Pandas", "NumPy", "Power BI", "Tableau", "Machine Learning"):
            self.assertIn(tool, s["Skills"], tool)
        self.assertEqual(s["Learning"], ["dbt", "Kafka", "Terraform"])
        self.assertNotIn("Terraform", s["Skills"])  # only learning and "planned" lines name it
        self.assertNotIn("CI/CD", s["Skills"])      # named only on a planned line

    def test_nothing_found_gives_nothing(self):
        self.assertEqual(importer.rule_skills("I like long walks and good coffee."), {})


class ProfileGapsTests(unittest.TestCase):
    def test_empty_profile_is_flagged(self):
        self.assertIn("same score", profile_gaps(EMPTY))

    def test_learning_only_still_counts_as_empty(self):
        self.assertIn("same score", profile_gaps({**EMPTY, "skills": {"Learning": ["dbt"]}}))

    def test_skills_without_work_get_a_milder_note(self):
        msg = profile_gaps({**EMPTY, "skills": {"Skills": ["Python"]}})
        self.assertIn("no jobs or projects", msg)
        self.assertNotIn("same score", msg)

    def test_full_profile_is_fine(self):
        full = {**EMPTY, "skills": {"Skills": ["Python"]}, "projects": [{"name": "P", "bullets": ["Python"]}]}
        self.assertEqual(profile_gaps(full), "")
        self.assertEqual(profile_gaps({}), "")  # a missing profile has its own message

    def test_rule_skills_make_keyword_scores_differ(self):
        prof = {**EMPTY, "skills": importer.rule_skills(CV)}
        data = keyword_score({"title": "Junior Data Engineer", "description": "Python, SQL, AWS Glue, Databricks"}, prof)
        other = keyword_score({"title": "Junior Controller", "description": "SAP and Excel for monthly closing"}, prof)
        self.assertGreater(data["match"], other["match"])


class ImportWithoutAITests(unittest.TestCase):
    def test_import_saves_skills_and_cv_text(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "cv.txt").write_text(CV, encoding="utf-8")
            out, notes = importer.import_cv(home / "cv.txt", Settings(home))
            prof = tomllib.loads(out.read_text(encoding="utf-8"))
            self.assertIn("Python", prof["skills"]["Skills"])
            self.assertEqual(prof["skills"]["Learning"], ["dbt", "Kafka", "Terraform"])
            self.assertIn("tool names", notes[0])
            src = home / importer.CV_SOURCE
            self.assertEqual(src.read_text(encoding="utf-8"), CV)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(src.stat().st_mode), 0o600)

    def test_saved_text_falls_back_to_imported_comments(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            body = importer.to_toml({"person": {"name": "X"}}, ["note"], source_text=CV)
            (home / "profile.imported.toml").write_text(body, encoding="utf-8")
            text = importer.saved_cv_text(home)
            self.assertIn("Currently Learning: dbt, Apache Kafka, Terraform", text)
            self.assertIn("Built dashboards in Power BI and Tableau.", text)
            self.assertEqual(importer.saved_cv_text(Path(d) / "nothing"), "")


class ChecksTests(unittest.TestCase):
    def test_setup_check_flags_empty_profile(self):
        with tempfile.TemporaryDirectory() as d:
            settings = Settings(Path(d))
            settings.profile = EMPTY
            with mock.patch("stellenpilot.cli.llm_status", return_value=(True, "none")):
                cv = next(c for c in setup_checks(settings) if c["step"] == "cv")
            self.assertFalse(cv["ok"])
            self.assertIn("same score", cv["text"])


AI_PROFILE = {"person": {"name": "Sourav Sarker"}, "skills": {"Languages": ["Python", "SQL"]},
              "experience": [{"title": "Junior Data Analyst", "company": "Techmak Technology", "dates": "2020 to 2023",
                              "bullets": ["Built dashboards in Power BI and Tableau."]}],
              "projects": [], "education": []}


class FakeLLM:
    enabled, local, provider, model, max_chars = True, True, "ollama", "fake", 4000

    def __init__(self, *a, **k):
        pass

    def complete_json(self, *a, **k):
        return AI_PROFILE


class RereadServerTests(unittest.TestCase):
    def _post(self, base, path, body):
        req = urllib.request.Request(f"{base}{path}", data=json.dumps(body).encode(), method="POST",
                                     headers={"X-Jobhunt": "1", "Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=10))

    def test_turning_on_ai_offers_and_runs_a_reread(self):
        from http.server import ThreadingHTTPServer
        from stellenpilot.server import make_handler, reread_offer
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            home = Path(d)
            (home / "profile.toml").write_text(importer.to_toml({"person": {"name": "Sourav Sarker"}}, None), encoding="utf-8")
            (home / importer.CV_SOURCE).write_text(CV, encoding="utf-8")
            settings = Settings(home)
            self.assertFalse(reread_offer(settings))  # no AI yet
            srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(settings))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            try:
                with self.assertRaises(urllib.error.HTTPError) as e:
                    self._post(base, "/api/cv/reread", {})
                self.assertEqual(e.exception.code, 400)
                r = self._post(base, "/api/settings", {"llm": {"provider": "ollama", "model": "fake"}})
                self.assertTrue(r["rereadOffer"])
                page = json.load(urllib.request.urlopen(f"{base}/api/settings", timeout=10))
                self.assertTrue(page["rereadOffer"])  # shown when Settings opens, not only right after a save
                with mock.patch("stellenpilot.llm.LLM", FakeLLM):
                    r = self._post(base, "/api/cv/reread", {})
                self.assertEqual(r["profile"]["experience"][0]["company"], "Techmak Technology")
                saved = tomllib.loads((home / "profile.toml").read_text(encoding="utf-8"))
                self.assertEqual(saved["experience"][0]["title"], "Junior Data Analyst")
                self.assertTrue((home / "profile.backup.toml").exists())
                self.assertFalse(reread_offer(settings))  # a filled profile is never replaced again
            finally:
                srv.shutdown()


if __name__ == "__main__":
    unittest.main()
