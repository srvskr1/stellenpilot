"""Fail if docs/tools/german-level.js reads a German requirement differently from the engine.

Runs every phrase from tests/test_german.py, plus a few longer ads, through
stellenpilot.text.required_german_level() and through the JS port (needs node).
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from stellenpilot.text import required_german_level  # noqa: E402
from tests.test_german import CASES, ReviewPhraseTests  # noqa: E402

phrases = list(CASES) + list(ReviewPhraseTests.CASES) + [
    "Sichere Deutschkenntnisse in Wort und Schrift runden Dein Profil ab.",
    "Languages: Fluent English (German is a bonus), a collaborative mindset.",
    "Currently enrolled at a German university and able to commute.",
    "Was du mitbringst: Studium der Informatik. Erste Erfahrung mit Python und SQL.\nGute Englischkenntnisse; Deutsch auf C1-Niveau.",
    "We offer a modern office in Essen. Requirements: 2 years of experience, fluent English. German skills (B1) are a plus.",
    "Du bringst Erfahrung mit Airflow mit. Deutsch fließend, Englisch gut.",
]
js = (ROOT / "docs/tools/german-level.js").as_posix()
script = f"const f=require({json.dumps(js)});const p=JSON.parse(require('fs').readFileSync(0,'utf8'));console.log(JSON.stringify(p.map(t=>f(t).level)))"
got = json.loads(subprocess.run(["node", "-e", script], input=json.dumps(phrases), capture_output=True, text=True, check=True).stdout)
bad = [(t, required_german_level(t), g) for t, g in zip(phrases, got) if required_german_level(t) != g]
for t, want, g in bad:
    print(f"MISMATCH engine={want} js={g}: {t!r}")
if bad:
    sys.exit(1)
print(f"ok: {len(phrases)} phrases match the engine")
