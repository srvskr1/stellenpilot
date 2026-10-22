"""What to learn next: unlocks() ranking and CV layouts."""
import tempfile
import tomllib
import unittest
from datetime import date
from importlib import resources
from pathlib import Path

from docx import Document

from stellenpilot.score import is_must_have, keyword_score, unlocks
from stellenpilot.tailor import tailor_job

PROFILE = tomllib.loads(resources.files("stellenpilot").joinpath("examples/profile.example.toml").read_text(encoding="utf-8"))
TODAY = date(2026, 10, 22)


def job(i, desc, title="Data Engineer", found="2026-10-01"):
    j = {"id": f"j{i}", "title": title, "company": f"Co {i}", "location": "Essen", "description": desc,
         "found_at": found, "closed": 0, "german_level": ""}
    j.update(keyword_score(j, PROFILE))
    return j


class UnlockTests(unittest.TestCase):
    def test_must_have_versus_nice_to_have(self):
        self.assertTrue(is_must_have("Kafka experience is required.", "Kafka"))
        self.assertFalse(is_must_have("Kafka is nice to have.", "Kafka"))
        self.assertTrue(is_must_have("Gute Deutschkenntnisse setzen wir voraus.", "German"))

    def test_ranks_the_skill_that_lifts_most_jobs(self):
        kafka = [job(i, "We use Python and SQL. Kafka experience is required.") for i in range(40)]
        looker = [job(100 + i, "Python and SQL daily. Looker is nice to have.") for i in range(15)]
        self.assertTrue(all(j["match"] < 70 for j in kafka + looker))
        out = unlocks(kafka + looker, PROFILE, 70, TODAY)
        self.assertTrue(out["enough"])
        self.assertEqual(out["rows"][0]["skill"], "Kafka")
        self.assertEqual((out["rows"][0]["jobs"], out["rows"][0]["must"]), (40, 40))
        self.assertEqual(out["rows"][1]["must"], 0)

    def test_old_closed_and_too_few_jobs_give_no_ranking(self):
        old = [job(i, "Python, SQL, Kafka required.", found="2026-05-01") for i in range(60)]
        out = unlocks(old, PROFILE, 70, TODAY)
        self.assertEqual((out["enough"], out["jobs"]), (False, 0))

    def test_ai_scored_job_counts_only_with_one_gap_near_the_line(self):
        base = [job(i, "Python, SQL, Kafka required.") for i in range(50)]
        ai = [{**job(200, "x"), "why": "Good fit.", "match": 60, "gap_tags": ["Snowflake"]},
              {**job(201, "x"), "why": "Good fit.", "match": 60, "gap_tags": ["Snowflake", "Kafka"]},
              {**job(202, "x"), "why": "Good fit.", "match": 40, "gap_tags": ["Snowflake"]}]
        rows = {r["skill"]: r["jobs"] for r in unlocks(base + ai, PROFILE, 70, TODAY)["rows"]}
        self.assertEqual(rows.get("Snowflake"), 1)


class CvStyleTests(unittest.TestCase):
    def test_lebenslauf_uses_german_headings(self):
        j = job(1, "Python, SQL and Airflow.")
        with tempfile.TemporaryDirectory() as d:
            res = tailor_job({**j, "url": "", "source": "t"}, PROFILE, Path(d), make_pdf=False, cv_style="lebenslauf")
            text = "\n".join(p.text for p in Document(res["files"][0]).paragraphs)
        self.assertEqual(res["cv_style"], "lebenslauf")
        self.assertIn("BERUFSERFAHRUNG", text)

    def test_unknown_style_falls_back_to_classic(self):
        j = job(2, "Python and SQL.")
        with tempfile.TemporaryDirectory() as d:
            res = tailor_job({**j, "url": "", "source": "t"}, PROFILE, Path(d), make_pdf=False, cv_style="fancy")
        self.assertEqual(res["cv_style"], "classic")


if __name__ == "__main__":
    unittest.main()
