"""Both TOML writers share one encoder (issue #21). Everything written must load back unchanged."""
import tempfile
import tomllib
import unittest
from pathlib import Path

from stellenpilot.config import dump_toml, save_user_config, toml_key, toml_str
from stellenpilot.importer import to_toml

TRICKY = {
    "quotes": 'He said "hi" and \'bye\'',
    "backslash": r"C:\Users\Sourav\cv.pdf",
    "umlauts": "Köln, Düsseldorf, Straße, Ärger",
    "newline and tab": "line one\nline two\tend",
    "DEL from a PDF": "Data\x7fEngineer",
    "other control": "a\x00b\x1bc",
    "emoji": "Data 🚀",
    "line separator": "a\u2028b",
    "looks like toml": 'x = 1\n[evil]\ny = "z"',
}


class EncoderTests(unittest.TestCase):
    def test_every_tricky_string_round_trips(self):
        for name, v in TRICKY.items():
            with self.subTest(name):
                self.assertEqual(tomllib.loads(f"k = {toml_str(v)}")["k"], v)

    def test_keys(self):
        self.assertEqual(toml_key("max_age_days"), "max_age_days")
        for k in ("größe", "a.b", "my key", "", 'say "x"'):
            with self.subTest(k):
                self.assertEqual(tomllib.loads(f"{toml_key(k)} = 1"), {k: 1})


class DumpTomlTests(unittest.TestCase):
    def test_nested_tables_and_types(self):
        data = {"top": "x", "search": {"keywords": ["Werkstudent Data", "Daten"], "radius_km": 25, "remote": True,
                                       "score": 0.5, "deeper": {"even": {"deepest": "ö"}}},
                "weird key": {"größe": TRICKY["quotes"]}}
        self.assertEqual(tomllib.loads(dump_toml(data)), data)

    def test_all_tricky_values(self):
        self.assertEqual(tomllib.loads(dump_toml({"t": TRICKY})), {"t": TRICKY})

    def test_none_is_left_out_not_written_as_text(self):
        self.assertEqual(tomllib.loads(dump_toml({"a": None, "b": 1, "s": {"c": None}})), {"b": 1, "s": {}})

    def test_list_of_tables(self):
        data = {"watch": [{"name": "Bosch", "id": 1}, {"name": "Köln AG", "id": 2}]}
        self.assertEqual(tomllib.loads(dump_toml(data)), data)

    def test_save_user_config_keeps_umlauts_and_quotes(self):
        with tempfile.TemporaryDirectory() as d:
            save_user_config(Path(d), {"search": {"city": "Köln", "keywords": ['Data "Engineer"']}})
            saved = tomllib.loads((Path(d) / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(saved["search"], {"city": "Köln", "keywords": ['Data "Engineer"']})


class ProfileTomlTests(unittest.TestCase):
    def profile(self, s):
        return {"person": {"name": s, "email": "a@b.de", "phone": "", "location": s, "links": [s], "languages": [s],
                           "headlines": [s], "summary": s},
                "skills": {s: [s, "SQL"]},
                "experience": [{"title": s, "company": s, "dates": "2020 to 2023", "bullets": [s, "Built pipelines"]}],
                "projects": [{"name": s, "link": "", "bullets": [s]}],
                "education": [{"degree": s, "school": s, "dates": "2016 to 2020"}]}

    def test_every_tricky_string_round_trips_in_every_field(self):
        for name, s in TRICKY.items():
            with self.subTest(name):
                p = self.profile(s)
                back = tomllib.loads(to_toml(p, ["check " + s], source_text=s))
                self.assertEqual(back["person"], p["person"])
                self.assertEqual(back["skills"], p["skills"])
                self.assertEqual(back["experience"], p["experience"])
                self.assertEqual(back["projects"], p["projects"])
                self.assertEqual(back["education"], p["education"])
                self.assertEqual(set(back), {"person", "skills", "experience", "projects", "education"})  # nothing injected

    def test_comments_are_kept_for_the_reader(self):
        text = to_toml(self.profile("Sourav"), ["Dates look odd"], source_text="Original CV line")
        self.assertIn("# CHECK THESE:", text)
        self.assertIn("#   Dates look odd", text)
        self.assertIn("# Original CV line", text)

    def test_missing_values_are_empty_not_none(self):
        back = tomllib.loads(to_toml({"person": {"name": "A", "email": None}}, None))
        self.assertEqual(back["person"]["email"], "")


if __name__ == "__main__":
    unittest.main()
