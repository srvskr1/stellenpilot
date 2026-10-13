import os
import tempfile
import tomllib
import unittest
from pathlib import Path

from stellenpilot.config import DEFAULTS, dump_toml, save_secrets, save_user_config
from stellenpilot.server import clean_settings, find_doc


class SettingsTest(unittest.TestCase):
    def test_dump_round_trip(self):
        self.assertEqual(tomllib.loads(dump_toml(DEFAULTS)), DEFAULTS)

    def test_clean_keeps_types_and_drops_unknown(self):
        out = clean_settings({"search": {"radius_km": "40", "keywords": ["a", " ", "b"], "country": "DE", "evil": 1},
                              "llm": {"provider": "ollama"}, "gmail": {"enabled": True}})
        self.assertEqual(out, {"search": {"radius_km": 40, "keywords": ["a", "b"], "country": "de"}, "llm": {"provider": "ollama"}})

    def test_clean_rejects_bad_values(self):
        for bad in ({"llm": {"provider": "rm -rf"}}, {"search": {"country": "germany"}},
                    {"search": {"radius_km": "far"}}, {"search": {"keywords": []}}):
            with self.assertRaises(ValueError):
                clean_settings(bad)

    def test_save_config_and_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "config.toml").write_text('[search]\ncity = "Berlin"\n[gmail]\nenabled = true\n', encoding="utf-8")
            cfg = save_user_config(home, {"search": {"city": "Essen"}})
            self.assertEqual(cfg["search"]["city"], "Essen")
            self.assertTrue(cfg["gmail"]["enabled"])  # untouched settings survive
            self.assertTrue((home / "config.backup.toml").exists())
            (home / ".env").write_text("# keys\nADZUNA_APP_ID=old\nOTHER=1\n", encoding="utf-8")
            save_secrets(home, {"ADZUNA_APP_ID": "new", "ADZUNA_APP_KEY": "", "THEIRSTACK_API_KEY": "t"})
            env = (home / ".env").read_text(encoding="utf-8")
            self.assertIn("ADZUNA_APP_ID=new", env)
            self.assertIn("OTHER=1", env)
            self.assertNotIn("ADZUNA_APP_KEY", env)  # empty means keep, nothing written
            self.assertEqual(os.environ.get("THEIRSTACK_API_KEY"), "t")
            with self.assertRaises(ValueError):
                save_secrets(home, {"X": "a\nEVIL=1"})
            os.environ.pop("THEIRSTACK_API_KEY", None)
            os.environ.pop("ADZUNA_APP_ID", None)


class FindDocTest(unittest.TestCase):
    def test_pdf_first_and_stays_in_output(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d).resolve() / "output"
            f = out / "2026-10-13" / "Acme__Data"
            f.mkdir(parents=True)
            for n in ("Jo_CV_Acme.docx", "Jo_CV_Acme.pdf", "Jo_Anschreiben_Acme.docx", "report.md"):
                (f / n).write_text("x")
            job = {"folder": str(f)}
            self.assertEqual(find_doc(job, "cv", out).name, "Jo_CV_Acme.pdf")
            self.assertEqual(find_doc(job, "letter", out).name, "Jo_Anschreiben_Acme.docx")
            self.assertIsNone(find_doc(job, "report", out))
            self.assertIsNone(find_doc({"folder": d}, "cv", out))  # outside the output folder
            self.assertIsNone(find_doc({"folder": ""}, "cv", out))


if __name__ == "__main__":
    unittest.main()
