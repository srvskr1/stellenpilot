"""Sorting a CV fast: rules first, then the AI answering with line numbers, then the old way.

The AI answers below were recorded from the built-in models (Light: Qwen3.5 2B, Standard: Qwen3.5 4B)
on these sample CVs."""
import unittest
from pathlib import Path

from stellenpilot import cv_parse as cp
from stellenpilot.importer import IMPORT_SYSTEM, sort_cv, verify

SAMPLES = Path(__file__).parent / "cv_samples"


def sample(name: str) -> str:
    return (SAMPLES / name).read_text(encoding="utf-8")


RECORDED = {  # what the Light model answered to LINES_SYSTEM
    "data_engineer_en.txt": {"summary": [4, 5, 8], "skills": [10, 11, 12, 13, 14, 15, 16, 17], "experience": [19, 24],
                             "projects": [32, 41, 52], "education": [58, 61]},
    "german.txt": {"summary": [6], "skills": [21, 22], "experience": [8, 9, 13], "projects": [], "education": [16, 17, 18]},
    "no_bullets.txt": {"summary": [1, 2, 3, 5, 6, 7, 9, 10, 12, 13, 15, 16], "skills": [15, 16], "experience": [6, 9],
                       "projects": [], "education": [13]},
}


class FakeLLM:
    enabled = True

    def __init__(self, lines_answer, full_answer=None):
        self.lines_answer, self.full_answer, self.calls = lines_answer, full_answer or {}, []

    def complete_json(self, system, user, max_tokens=1500):
        self.calls.append("lines" if system == cp.LINES_SYSTEM else "full" if system == IMPORT_SYSTEM else "?")
        return self.lines_answer if system == cp.LINES_SYSTEM else self.full_answer


def summary(p):
    return {"jobs": [(e["title"], e["company"], e["dates"], len(e["bullets"])) for e in p["experience"]],
            "projects": [(x["name"], x["link"], len(x["bullets"])) for x in p["projects"]],
            "education": [(e["degree"], e["school"], e["dates"]) for e in p["education"]]}


EXPECTED = {
    "data_engineer_en.txt": {
        "jobs": [("ICQA Associate", "Example Retail", "Jul 2024 to Present", 2),
                 ("Junior Data Analyst", "Example Tech", "Sep 2020 to Sep 2023", 3)],
        "projects": [("German Train Delays: Azure Data Pipeline", "github.com/alex-example/db-delays-azure-pipeline", 3),
                     ("NYC Taxi: AWS Serverless Data Pipeline", "github.com/alex-example/nyc-taxi-aws-pipeline", 4),
                     ("Weather ETL: Airflow Orchestration, Personal Project", "", 2)],
        "education": [("M.Sc. in Data Science", "Technical University of Example, Germany", "Oct 2023 to Present"),
                      ("B.Sc. in Software Engineering", "Example International University, Bangladesh", "Sep 2016 to Jan 2020")]},
    "german.txt": {
        "jobs": [("Werkstudentin Data Analytics", "Ruhr Energie GmbH", "seit 10/2024", 2),
                 ("Praktikantin Business Intelligence", "Westfalen Handel AG", "03/2023 – 08/2023", 1)],
        "projects": [],
        "education": [("M.Sc. Wirtschaftsinformatik", "Universität Duisburg-Essen", "10/2023 – heute"),
                      ("B.Sc. Wirtschaftsinformatik", "TU Dortmund", "10/2019 – 09/2023")]},
    "no_bullets.txt": {
        "jobs": [("Data Engineer", "Rhein Logistics", "2022 - Present", 1), ("Junior BI Developer", "Domstadt Retail", "2020 - 2022", 1)],
        "projects": [],
        "education": [("B.Sc. Computer Science", "University of Cologne", "2016 - 2020")]},
}


class RulesTests(unittest.TestCase):
    def test_clean_cvs_need_no_ai(self):
        for name, want in EXPECTED.items():
            with self.subTest(name):
                text = sample(name)
                prof, how, why = sort_cv(text, None)
                self.assertEqual(how, "rules", why)
                checked, notes = verify(prof, text)
                self.assertEqual(summary(checked), want)
                self.assertFalse([n for n in notes if "removed" in n], "rules copy text, so nothing may be dropped")

    def test_english_details(self):
        text = sample("data_engineer_en.txt")
        prof, _, _ = sort_cv(text, None)
        p = prof["person"]
        self.assertEqual((p["name"], p["location"]), ("ALEX KUMAR", "Essen, Germany"))
        self.assertEqual(p["headlines"], ["Data Engineer | Cloud Data Pipelines (AWS & Azure) | ETL/ELT | Analytics"])
        self.assertTrue(p["summary"].startswith("Data professional with 3+ years") and p["summary"].endswith("available immediately."))
        self.assertEqual(prof["skills"]["Learning"], ["dbt", "Apache Kafka", "Terraform"])
        self.assertIn("Parquet", prof["skills"]["Cloud & Data Engineering"])  # a line break after "Parquet," is not a skill
        self.assertIn("Azure (ADLS Gen2, Data Factory, Databricks, Azure SQL, Blob Storage)", prof["skills"]["Cloud & Data Engineering"])
        bullet = prof["projects"][1]["bullets"][0]
        self.assertTrue(bullet.endswith("over 2.96 million taxi trip records stored as Parquet."), bullet)

    def test_unclear_layout_is_partial_without_ai(self):
        prof, how, why = sort_cv(sample("messy_columns.txt"), None)
        self.assertEqual(how, "rules-partial")
        self.assertTrue(why)

    def test_headings(self):
        for line, want in (("Professional Experience", "experience"), ("Data Engineering Projects", "projects"),
                           ("Berufserfahrung", "experience"), ("Ausbildung", "education"), ("Kenntnisse", "skills"),
                           ("TECHNICAL SKILLS:", "skills"), ("Built dashboards in Power BI for the projects team.", None),
                           ("Education 2019", None), ("• Skills", None)):
            self.assertEqual(cp.heading_of(line), want, line)

    def test_dates(self):
        for line, want in (("Junior Data Analyst, Techmak    Sep 2020 to Sep 2023", ("Junior Data Analyst, Techmak", "Sep 2020 to Sep 2023")),
                           ("Werkstudent, Firma GmbH  seit 10/2024", ("Werkstudent, Firma GmbH", "seit 10/2024")),
                           ("Data Engineer at Rhein Logistics, 2022 - Present", ("Data Engineer at Rhein Logistics", "2022 - Present")),
                           ("Praktikum (03.2023 – 08.2023)", ("Praktikum", "03.2023 – 08.2023")),
                           ("No dates here", ("No dates here", ""))):
            self.assertEqual(cp.split_dates(line), want, line)


UNUSUAL = {"summary": [], "skills": [15], "experience": [5, 8], "projects": [], "education": [12]}  # Standard model


class LineNumberTests(unittest.TestCase):
    def test_unknown_headings_are_sorted_by_line_numbers(self):
        text = sample("unusual_headings.txt")
        self.assertEqual(sort_cv(text, None)[1], "rules-partial")  # "Where I have worked" is no heading the rules know
        llm = FakeLLM(UNUSUAL)
        prof, how, _ = sort_cv(text, llm)
        self.assertEqual((how, llm.calls), ("ai-lines", ["lines"]))
        checked, notes = verify(prof, text)
        self.assertEqual(summary(checked), {
            "jobs": [("Analytics Engineer", "Kölner Mobil GmbH", "Jan 2023 – Present", 2),
                     ("Data Analyst", "Rheinland Versicherung", "Aug 2020 – Dec 2022", 1)],
            "projects": [],
            "education": [("M.Sc. Data Science", "Heinrich Heine University Düsseldorf", "2018 – 2020")]})
        self.assertEqual(checked["person"]["name"], "Priya Nair")
        self.assertFalse([n for n in notes if "removed" in n])

    def test_recorded_answers_give_the_same_profile_as_the_rules(self):
        for name, answer in RECORDED.items():
            with self.subTest(name):
                text = sample(name)
                sections, entries = cp.by_line_numbers(answer, text)
                prof = cp.build(sections, {"name": ""}, entries)
                checked, notes = verify(prof, text)
                self.assertEqual(summary(checked), EXPECTED[name])
                self.assertFalse([n for n in notes if "removed" in n])

    def test_summary_list_cannot_swallow_the_cv(self):
        text = sample("no_bullets.txt")
        sections, _ = cp.by_line_numbers(RECORDED["no_bullets.txt"], text)
        self.assertEqual(sections["summary"], [])  # the model listed nearly every line as "summary"
        self.assertEqual([i["text"] for i in sections["top"]][0], "Max Mustermann")

    def test_ai_is_used_only_when_the_rules_are_unsure(self):
        llm = FakeLLM(RECORDED["data_engineer_en.txt"])
        _, how, _ = sort_cv(sample("data_engineer_en.txt"), llm)
        self.assertEqual((how, llm.calls), ("rules", []))

    def test_line_numbers_then_full_ai_as_last_resort(self):
        text = sample("messy_columns.txt")
        good = {"experience": [3], "education": [6]}
        llm = FakeLLM(good, full_answer={"experience": [{"title": "Data Scientist", "company": "Bonn Analytics GmbH",
                                                          "dates": "2021 – 2024", "bullets": []}]})
        prof, how, _ = sort_cv(text, llm)
        # Columns run into each other, so the line ranges give a job without a company: ask for the full answer.
        self.assertEqual((how, llm.calls), ("ai-full", ["lines", "full"]))
        self.assertEqual(prof["experience"][0]["company"], "Bonn Analytics GmbH")

    def test_nonsense_answer_falls_back(self):
        llm = FakeLLM({"summary": ["Data professional with 3+ years"], "experience": "lots"}, full_answer={})
        _, how, _ = sort_cv(sample("messy_columns.txt"), llm)
        self.assertEqual(how, "ai-full")

    def test_numbers_are_parsed_leniently(self):
        self.assertEqual(cp._nums([3, "4", [7, 8], 99, "x", 2.0], 10), [2, 3, 4, 7, 8])


if __name__ == "__main__":
    unittest.main()
