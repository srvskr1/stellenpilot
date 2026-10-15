"""Offline tests for `stellenpilot eval`."""
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from stellenpilot import evaluate as ev
from stellenpilot.cli import main
from stellenpilot.config import Settings
from stellenpilot.db import DB


def _job(i, match, desc="Python SQL Airflow AWS", **kw):
    return {"id": i, "source": "Test", "title": f"Data Engineer {i}", "company": f"Co {i}", "location": "Essen",
            "remote": False, "url": f"https://example.com/{i}", "posted_at": "", "description": desc,
            "match": match, "dedupe_key": i, **kw}


class StatsTests(unittest.TestCase):
    def test_ranks_average_ties(self):
        self.assertEqual(ev.ranks([10, 20, 20, 30]), [1, 2.5, 2.5, 4])

    def test_perfect_and_reversed_ranking(self):
        self.assertAlmostEqual(ev.spearman([1, 2, 3, 4], [0, 1, 2, 3]), 1.0)
        self.assertAlmostEqual(ev.auc([90, 80, 20, 10], [True, True, False, False]), 1.0)
        self.assertAlmostEqual(ev.auc([10, 20, 80, 90], [True, True, False, False]), 0.0)

    def test_constant_score_cannot_rank(self):
        self.assertIsNone(ev.spearman([50, 50, 50, 50], [0, 1, 0, 1]))
        self.assertAlmostEqual(ev.auc([50, 50, 50, 50], [True, False, True, False]), 0.5)

    def test_auc_needs_both_classes(self):
        self.assertIsNone(ev.auc([1, 2], [True, True]))

    def test_precision_at_k(self):
        self.assertAlmostEqual(ev.precision_at_k([90, 80, 70, 10], [True, False, True, False], 2), 0.5)

    def test_min_match_decision(self):
        m = ev.metrics([90, 75, 60, 40], [1, 0, 1, 0], threshold=1, min_match=70, k=2)
        self.assertEqual(m["passed_min_match"], 2)
        self.assertAlmostEqual(m["recall_at_min_match"], 0.5)
        self.assertAlmostEqual(m["precision_at_min_match"], 0.5)


class LabelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.db = DB(self.home / "jobhunt.db")

    def tearDown(self):
        self.db.conn.close()
        self.tmp.cleanup()

    def test_labels_from_ratings_and_outcomes(self):
        self.db.insert_job(_job("a", 80, rating=1))
        self.db.insert_job(_job("b", 70, status="interview"))
        self.db.insert_job(_job("c", 60, rating=-1))
        self.db.insert_job(_job("d", 50, status="rejected"))
        self.db.insert_job(_job("e", 40, rating=-1, status="interview"))  # conflicting: left out
        self.db.insert_job(_job("f", 30))
        self.assertEqual(ev.labels_from_db(self.db), {"a": 1.0, "b": 1.0, "c": 0.0})
        self.assertEqual(ev.labels_from_db(self.db, include_rejected=True)["d"], 0.0)

    def test_csv_labels_saved_by_german_excel(self):
        # Excel in German: ';' separator, Windows-1252, and a 'Column1;...' line above the header.
        p = self.home / "excel.csv"
        p.write_bytes("Column1;Column2;Column3\nid;label;title\na;1;Müller\nb;0;x\nc;;y\n".encode("cp1252"))
        self.assertEqual(ev.labels_from_csv(p), {"a": 1.0, "b": 0.0})

    def test_csv_labels_skip_empty_and_reject_text(self):
        p = self.home / "l.csv"
        p.write_text("id,label,title\na,1,x\nb,,y\nc,0,z\n", encoding="utf-8")
        self.assertEqual(ev.labels_from_csv(p), {"a": 1.0, "c": 0.0})
        p.write_text("id,label\na,good\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            ev.labels_from_csv(p)
        p.write_text("job,score\na,1\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            ev.labels_from_csv(p)

    def test_sheet_spreads_over_scores_and_hides_them(self):
        for i in range(50):
            self.db.insert_job(_job(f"j{i}", 95 if i < 40 else i))  # most jobs score high
        p = self.home / "eval" / "labels.csv"
        self.assertEqual(ev.make_sheet(self.db, p, n=20), 20)
        rows = list(csv.DictReader(open(p, encoding="utf-8")))
        self.assertNotIn("stored_match", rows[0])
        low = [r for r in rows if int(r["id"][1:]) >= 40]
        self.assertGreaterEqual(len(low), 8)  # the rare low scores are not crowded out


class FakeLLM:
    """Scores a job by its stored 'truth' hidden in the description: a perfect model."""
    enabled, local, provider, model, max_chars = True, True, "fake", "perfect", 4000

    def complete_json(self, system, user, max_tokens=600):
        return {"match": 90 if "GOOD" in user else 20, "fit": "x", "why": "y", "gaps": "", "gap_tags": []}

    def complete(self, *a, **k):
        return ""


@mock.patch.dict(os.environ)  # init writes an empty .env that Settings loads; keep it out of other tests
class EndToEndTests(unittest.TestCase):
    def test_eval_reports_and_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            main(["--home", str(home), "init"])
            db = DB(home / "jobhunt.db")
            for i in range(12):
                good = i % 2 == 0
                db.insert_job(_job(f"j{i}", 50, desc=("GOOD " if good else "") + "Python SQL", rating=1 if good else -1))
            db.conn.close()
            settings = Settings(home)
            with mock.patch("stellenpilot.llm.LLM", side_effect=lambda s: FakeLLM()):
                report = ev.evaluate(settings, providers=["ollama:fake"], out_dir=home / "eval" / "run")
            res = report["results"]
            self.assertEqual(list(res), ["stored", "keyword", "fake:perfect"])
            self.assertAlmostEqual(res["fake:perfect"]["auc"], 1.0)
            self.assertAlmostEqual(res["stored"]["auc"], 0.5)  # every stored score is 50
            self.assertEqual(res["stored"]["distinct_scores"], 1)
            text = ev.format_report(report)
            self.assertIn("only 1 different scores", text)
            saved = json.loads((home / "eval" / "run" / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["n_jobs"], 12)
            self.assertTrue((home / "eval" / "run" / "scores.csv").exists())

    def test_no_labels_gives_a_clear_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            main(["--home", str(home), "init"])
            self.assertEqual(main(["--home", str(home), "eval", "--no-llm"]), 1)

    def test_one_kind_of_label_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            main(["--home", str(home), "init"])
            db = DB(home / "jobhunt.db")
            db.insert_job(_job("a", 80, rating=1))
            db.insert_job(_job("b", 60, rating=1))
            db.conn.close()
            with self.assertRaisesRegex(ValueError, "nothing to rank"):
                ev.evaluate(Settings(home), use_config_llm=False)

    def test_provider_spec(self):
        self.assertEqual(ev.parse_provider("ollama:qwen3.5:4b"), {"provider": "ollama", "model": "qwen3.5:4b"})
        self.assertEqual(ev.parse_provider("anthropic"), {"provider": "anthropic", "model": ""})


if __name__ == "__main__":
    unittest.main()
