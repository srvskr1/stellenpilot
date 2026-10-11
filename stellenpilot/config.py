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
    "language": {"skip_if_german_too_high": True, "my_german_level": "", "german_tolerance": 1},
    "sources": {
        "arbeitsagentur": True,
        "arbeitnow": True,
        "adzuna": False,
        "theirstack": False,
        "jobicy": True,
        "remotive": True,
        "limits": {"adzuna_calls": 20, "adzuna_pages": 5, "theirstack_jobs": 6, "arbeitsagentur_results": 150,
                   "arbeitsagentur_pages": 5, "arbeitnow_pages": 10, "jobicy_pages": 3},
        "theirstack_options": {"location_ids": [], "english_only": True},
    },
    "llm": {"provider": "none", "model": "", "base_url": ""},
    "tailor": {"min_match": 70, "max_per_run": 5, "output_dir": "output", "make_pdf": True, "only_english_ads": True, "letter_language": "auto"},
    "gmail": {"enabled": False, "lookback_days": 3},
    "watch": {"companies": [], "starter_list": False, "title_words": [], "max_age_days": 30},
    "notify": {"email": False, "telegram": False, "only_when_new": False},
    "schedule": {"enabled": False, "time": "08:45"},
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


# ---------------------------------------------------------------- saving from the dashboard

def _toml_value(v) -> str:
    import json
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)  # JSON strings are valid TOML basic strings


def dump_toml(data: dict, prefix: str = "") -> str:
    import json
    key = lambda k: k if k.replace("_", "").replace("-", "").isalnum() else json.dumps(k, ensure_ascii=False)
    lines = [f"{key(k)} = {_toml_value(v)}" for k, v in data.items() if not isinstance(v, dict)]
    for k, v in data.items():
        if isinstance(v, dict):
            name = f"{prefix}.{key(k)}" if prefix else key(k)
            lines += ["", f"[{name}]", dump_toml(v, name).strip("\n")]
    return "\n".join(lines).strip("\n") + "\n"


def save_user_config(home: Path, updates: dict) -> dict:
    """Merge updates into config.toml, keep a backup, return the new merged config."""
    path = home / "config.toml"
    user = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    user = _merge(user, updates)
    body = ("# Saved from the dashboard. Every option is explained in config.example.toml in the project.\n\n"
            + dump_toml(user))
    tomllib.loads(body)  # never write a file that would not load
    if path.exists():
        path.replace(home / "config.backup.toml")
    path.write_text(body, encoding="utf-8")
    return _merge(DEFAULTS, user)


def save_secrets(home: Path, secrets: dict) -> None:
    """Set keys in .env, keeping every other line. Empty values are ignored (keep the old key)."""
    secrets = {k: v.strip() for k, v in secrets.items() if v and v.strip()}
    if not secrets:
        return
    for v in secrets.values():
        if "\n" in v or "\r" in v:
            raise ValueError("A key cannot contain a line break.")
    path = home / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    left = dict(secrets)
    for i, ln in enumerate(lines):
        name = ln.split("=", 1)[0].strip()
        if "=" in ln and not ln.lstrip().startswith("#") and name in left:
            lines[i] = f"{name}={left.pop(name)}"
    lines += [f"{k}={v}" for k, v in left.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ.update(secrets)
