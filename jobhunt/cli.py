"""Command line: jobhunt init | doctor | run | serve | gmail | demo"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from importlib import resources
from pathlib import Path

from .config import Settings

ENV_TEMPLATE = """# Secrets for job-hunt-pipeline. This file is ignored by git. Never commit it.
# LLM (pick one, matching llm.provider in config.toml)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
# Optional job sources
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
THEIRSTACK_API_KEY=
"""


def _examples_dir() -> Path:
    return Path(str(resources.files("jobhunt").joinpath("examples")))


def cmd_init(home: Path) -> None:
    ex = _examples_dir()
    for src, dst in (("config.example.toml", "config.toml"), ("profile.example.toml", "profile.toml")):
        target = home / dst
        if target.exists():
            print(f"keep  {dst} (already exists)")
        else:
            shutil.copy(ex / src, target)
            print(f"made  {dst}")
    env = home / ".env"
    if not env.exists():
        env.write_text(ENV_TEMPLATE, encoding="utf-8")
        print("made  .env (put your API keys here)")
    print("\nNext: edit profile.toml with your real CV facts, check config.toml, then run `jobhunt doctor`.")


def cmd_doctor(settings: Settings) -> int:
    from .sources import REGISTRY
    ok = True
    print(f"home: {settings.home}")
    print(f"config.toml: {'found' if (settings.home / 'config.toml').exists() else 'missing, using defaults'}")
    if not settings.profile:
        print("profile.toml: MISSING (run jobhunt init)"); ok = False
    elif settings.profile.get("person", {}).get("name") == "Alex Example":
        print("profile.toml: still the example profile. Replace it with your own facts.")
    else:
        print("profile.toml: ok")
    for name, mod in REGISTRY.items():
        on = settings["sources"].get(name)
        need = [k for k in getattr(mod, "NEEDS", ()) if not settings.secret(k)]
        state = "off" if not on else (f"ON but missing {', '.join(need)}" if need else "on")
        ok &= not (on and need)
        print(f"source {name:15} {state}")
    prov = settings["llm"]["provider"]
    key = {"anthropic": "ANTHROPIC_API_KEY"}.get(prov)
    print(f"llm: {prov}" + (" (missing ANTHROPIC_API_KEY)" if key and not settings.secret(key) else ""))
    from .tailor import find_soffice
    print(f"pdf export: {'LibreOffice found' if find_soffice() else 'LibreOffice not found, DOCX only'}")
    print(f"gmail: {'on' if settings['gmail'].get('enabled') else 'off'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="jobhunt", description="Local job hunt pipeline")
    ap.add_argument("--home", type=Path, default=Path.cwd(), help="folder with config.toml and profile.toml")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create config.toml, profile.toml and .env from the examples")
    sub.add_parser("doctor", help="check your setup")
    r = sub.add_parser("run", help="search, score, tailor and sync once")
    r.add_argument("--no-tailor", action="store_true", help="skip CV and letter generation")
    s = sub.add_parser("serve", help="open the local dashboard")
    s.add_argument("--port", type=int, default=8765)
    sub.add_parser("gmail", help="sync statuses from Gmail once")
    sub.add_parser("demo", help="load fictional sample jobs to try the dashboard without any keys")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(message)s")
    home = a.home.resolve()

    if a.cmd == "init":
        cmd_init(home)
        return 0
    settings = Settings(home)
    if a.cmd == "doctor":
        return cmd_doctor(settings)
    if a.cmd == "run":
        from .pipeline import run
        res = run(settings, tailor=not a.no_tailor)
        print(f"{res['new']} new jobs, {res['shortlisted']} shortlisted, {res['docs']} files made, "
              f"{len(res['gmail'])} Gmail updates")
        for p in res["problems"]:
            print(f"  problem: {p}")
        return 0
    if a.cmd == "serve":
        from .server import serve
        serve(settings, a.port)
        return 0
    if a.cmd == "gmail":
        from .db import DB
        from .gmail_sync import sync
        changes = sync(DB(settings.db_path), home, settings["gmail"].get("lookback_days", 3))
        print(f"{len(changes)} status changes")
        return 0
    if a.cmd == "demo":
        from .demo import load_demo
        n = load_demo(settings)
        print(f"Loaded {n} fictional jobs into {settings.db_path.name}. Now run: jobhunt serve")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
