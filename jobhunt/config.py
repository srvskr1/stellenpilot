"""Load config.toml, profile.toml and secrets from the environment or a .env file."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

DEFAULTS = {
    "search": {
        "keywords": ["Werkstudent Data", "Junior Data Engineer"],
        "city": "Berlin",
        "radius_km": 50,
        "nearby_cities": [],
        "country": "de",
        "include_remote": True,
        "max_age_days": 3,
        "exclude_title_words": ["senior", "lead", "head of", "principal"],
    },
    "language": {"skip_if_fluent_german_required": True},
    "sources": {
        "arbeitsagentur": True,
        "arbeitnow": True,
        "adzuna": False,
        "theirstack": False,
        "limits": {"adzuna_calls": 4, "theirstack_jobs": 6, "arbeitsagentur_results": 50},
        "theirstack_options": {"location_ids": [], "english_only": True},
    },
    "llm": {"provider": "none", "model": "claude-sonnet-4-5", "base_url": ""},
    "tailor": {"min_match": 70, "max_per_run": 5, "output_dir": "output", "make_pdf": True, "only_english_ads": True},
    "gmail": {"enabled": False, "lookback_days": 3},
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=value lines, existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if val[:1] in ("'", '"') and val[:1] in val[1:]:
            val = val[1:val.index(val[0], 1)]
        else:
            val = val.split(" #")[0].strip()
        os.environ.setdefault(key.strip(), val)


class Settings:
    def __init__(self, home: Path):
        self.home = home
        load_dotenv(home / ".env")
        cfg_path = home / "config.toml"
        user = tomllib.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        self.cfg = _merge(DEFAULTS, user)
        prof_path = home / "profile.toml"
        self.profile = tomllib.loads(prof_path.read_text(encoding="utf-8")) if prof_path.exists() else {}
        self.db_path = home / "jobhunt.db"

    def __getitem__(self, key):
        return self.cfg[key]

    @staticmethod
    def secret(name: str) -> str | None:
        val = os.environ.get(name, "").strip()
        return val or None
