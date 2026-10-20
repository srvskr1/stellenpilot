import os
import tempfile
import tomllib
import unittest
from pathlib import Path

from stellenpilot.config import DEFAULTS, dump_toml, save_secrets, save_user_config
from stellenpilot.server import check_credentials, clean_settings, find_doc


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


class CredentialsTest(unittest.TestCase):
    def test_only_desktop_clients(self):
        ok = '{"installed": {"client_id": "x.apps.googleusercontent.com", "client_secret": "s"}}'
        self.assertEqual(check_credentials(ok), ok)
        for bad, word in (("hello", "json"), ('{"web": {"client_id": "x"}}', "Desktop"), ("{}", "Desktop"), ("[]", "Desktop")):
            with self.assertRaises(ValueError) as cm:
                check_credentials(bad)
            self.assertIn(word, str(cm.exception))


if __name__ == "__main__":
    unittest.main()


class LanguageTest(unittest.TestCase):
    def test_ui_language_is_a_setting(self):
        self.assertEqual(clean_settings({"ui": {"language": "de"}}), {"ui": {"language": "de"}})
        self.assertEqual(DEFAULTS["ui"]["language"], "auto")

    def test_jobicy_default_matches_the_docs(self):
        # docs/sources.md, config.example.toml and jobicy.py all say 2 pages; the merged default must too.
        self.assertEqual(DEFAULTS["sources"]["limits"]["jobicy_pages"], 2)
        with self.assertRaises(ValueError):
            clean_settings({"ui": {"language": "fr"}})

    def test_page_gets_only_a_known_language(self):
        from stellenpilot.server import with_language
        page = b'<!doctype html>\n<html lang="en">\n<head>'
        self.assertIn(b'data-ui="de"', with_language(page, "de"))
        self.assertIn(b'data-ui="auto"', with_language(page, '"><script>'))  # never written into the HTML as is

    def test_every_code_string_has_a_german_text(self):
        """Strings passed to t() in the dashboard must be in the DE table, or German users see English."""
        import re
        html = (Path(__file__).parent.parent / "stellenpilot" / "web" / "index.html").read_text(encoding="utf-8")
        table = html[html.index("const DE={"):html.index("const n1=")]
        keys = {m.group(1).encode().decode("unicode_escape").encode("latin-1").decode("utf-8")
                for m in re.finditer(r'(?:^|[,{\n])\s*"((?:[^"\\]|\\.)*)":', table)}
        keys |= set(re.findall(r"'([^']*)':", table))
        code = html[html.index("const STAGES="):]
        used = set(re.findall(r"\bt\('([^']*)'", code))
        for call in re.findall(r'\bt\(((?:[^()"\']|"(?:[^"\\]|\\.)*")*?)(?:,\{|\))', code):
            call = re.sub(r'[=!]==\s*"(?:[^"\\]|\\.)*"', "", call)  # comparisons, not text
            used |= {s.encode().decode("unicode_escape").encode("latin-1").decode("utf-8")
                     for s in re.findall(r'"((?:[^"\\]|\\.)*)"', call)}
        missing = sorted(u for u in used if u and u not in keys)
        self.assertEqual(missing, [])

    def test_german_learning_group(self):
        from stellenpilot.score import is_learning_group
        self.assertTrue(is_learning_group("Learning"))
        self.assertTrue(is_learning_group("Lernen"))
        self.assertFalse(is_learning_group("Cloud"))
