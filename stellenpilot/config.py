"""Load config.toml, profile.toml and secrets from the environment or a .env file."""
from __future__ import annotations

import json
import os
import re
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
        "repost_after_days": 45,
    },
    "language": {"skip_if_german_too_high": True, "my_german_level": "", "german_tolerance": 1},
    "sources": {
        "arbeitsagentur": True,
        "arbeitnow": True,
        "adzuna": False,
        "theirstack": False,
        "jobicy": True,
        "remotive": True,
        "workingstudentjobs": True,
        "limits": {"adzuna_calls": 20, "adzuna_pages": 5, "theirstack_jobs": 6, "arbeitsagentur_results": 150,
                   "arbeitsagentur_pages": 5, "arbeitnow_pages": 10, "jobicy_pages": 2,
                   "workingstudentjobs_pages": 3},
        "theirstack_options": {"location_ids": [], "english_only": True},
    },
    "llm": {"provider": "none", "model": "", "base_url": ""},
    "tailor": {"min_match": 70, "max_per_run": 5, "output_dir": "output", "make_pdf": True, "only_english_ads": True, "letter_language": "auto"},
    "gmail": {"enabled": False, "lookback_days": 3, "method": "", "address": "", "imap_host": ""},
    "watch": {"companies": [], "starter_list": False, "title_words": [], "max_age_days": 30},
    "notify": {"email": False, "telegram": False, "only_when_new": False},
    "schedule": {"enabled": False, "time": "08:45"},
    "ui": {"language": "auto"},  # dashboard language: "auto" (from the browser), "en" or "de"
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


PRIVATE_FILES = (".env", "credentials.json", "token.json")


def write_private(path: Path, text: str) -> None:
    """Write a file only you can read (API keys, passwords, the Gmail token). On Windows the
    user folder is already private; on macOS and Linux files are otherwise readable by everyone."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    if os.name != "nt":
        os.chmod(path, 0o600)  # an existing file keeps its old mode through os.open


def tighten_private_files(home: Path) -> None:
    """Fix files saved by older versions with mode 644."""
    if os.name == "nt":
        return
    for name in PRIVATE_FILES:
        f = home / name
        try:
            if f.exists() and f.stat().st_mode & 0o077:
                os.chmod(f, 0o600)
        except OSError:
            pass


def _dotenv_value(v: str) -> str:
    """Quote a value when load_dotenv would otherwise cut it (spaces, #, quotes)."""
    if v and not any(c in v for c in " \t#'\""):
        return v
    for q in ('"', "'"):
        if q not in v:
            return f"{q}{v}{q}"
    raise ValueError("A key cannot contain both kinds of quotes.")


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
        tighten_private_files(home)
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

# One TOML encoder for keys and values, used by dump_toml here and by importer.to_toml (issue #21).
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def toml_str(v) -> str:
    """A TOML basic string. JSON escapes every control character TOML forbids except DEL, so that one is added."""
    return json.dumps(str(v), ensure_ascii=False).replace("\x7f", "\\u007f")


_COMMENT_BAD = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # TOML comments allow tab but no other control character


def toml_comment(text, prefix: str = "# ") -> list[str]:
    """Comment lines for any text: one per line, so a line break can never end the comment early."""
    lines = (_COMMENT_BAD.sub(" ", ln).rstrip() for ln in str(text or "").splitlines())
    return [prefix + ln for ln in lines if ln.strip()]


def toml_key(k) -> str:
    k = str(k)
    return k if _BARE_KEY.fullmatch(k) else toml_str(k)  # TOML bare keys are ASCII only, so "größe" is quoted


def toml_value(v) -> str:
    if v is None:
        raise ValueError("TOML has no empty value (None)")
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, dict):
        return "{" + ", ".join(f"{toml_key(k)} = {toml_value(x)}" for k, x in v.items() if x is not None) + "}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    return toml_str(v)


def dump_toml(data: dict, prefix: str = "") -> str:
    """Plain TOML for config.toml: values first, then one [table] per nested dict. None values are left out."""
    lines = [f"{toml_key(k)} = {toml_value(v)}" for k, v in data.items() if v is not None and not isinstance(v, dict)]
    for k, v in data.items():
        if isinstance(v, dict):
            name = f"{prefix}.{toml_key(k)}" if prefix else toml_key(k)
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


def save_secrets(home: Path, secrets: dict, clear: tuple[str, ...] | list[str] = ()) -> None:
    """Set keys in .env, keeping every other line. Empty values are ignored (keep the old key);
    names in `clear` are removed. The file is readable only by you."""
    secrets = {k: v.strip() for k, v in secrets.items() if v and v.strip() and k not in clear}
    clear = [k for k in clear if k]
    if not secrets and not clear:
        return
    for v in secrets.values():
        if "\n" in v or "\r" in v:
            raise ValueError("A key cannot contain a line break.")
    path = home / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    left = dict(secrets)
    out = []
    for ln in lines:
        name = ln.split("=", 1)[0].strip()
        if "=" in ln and not ln.lstrip().startswith("#"):
            if name in clear:
                continue
            if name in left:
                ln = f"{name}={_dotenv_value(left.pop(name))}"
        out.append(ln)
    out += [f"{k}={_dotenv_value(v)}" for k, v in left.items()]
    write_private(path, "\n".join(out) + "\n")
    os.environ.update(secrets)
    for k in clear:
        os.environ.pop(k, None)
