"""Command line: stellenpilot init | doctor | run | serve | gmail | demo | eval"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from importlib import resources
from pathlib import Path

from .config import Settings

ENV_TEMPLATE = """# Secrets for stellenpilot. This file is ignored by git. Never commit it.
# LLM (pick one, matching llm.provider in config.toml)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
# Optional job sources
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
THEIRSTACK_API_KEY=
# Optional daily digest to yourself (see docs/digest.md)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
DIGEST_TO=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
"""


def _examples_dir() -> Path:
    return Path(str(resources.files("stellenpilot").joinpath("examples")))


def cmd_init(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)  # `--home NEW_FOLDER init` must work, not only an existing folder
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
        from .config import write_private
        write_private(env, ENV_TEMPLATE)  # it will hold API keys and passwords
        print("made  .env (put your API keys here)")
    print("\nNext: edit profile.toml with your real CV facts, check config.toml, then run `stellenpilot doctor`.")


def cmd_doctor(settings: Settings) -> int:
    from .sources import REGISTRY
    ok = True
    print(f"home: {settings.home}")
    print(f"config.toml: {'found' if (settings.home / 'config.toml').exists() else 'missing, using defaults'}")
    if not settings.profile:
        print("profile.toml: MISSING (run stellenpilot init)"); ok = False
    elif settings.profile.get("person", {}).get("name") == "Alex Example":
        print("profile.toml: still the example profile. Replace it with your own facts.")
    else:
        from .score import profile_gaps
        gaps = profile_gaps(settings.profile)
        print(f"profile.toml: PROBLEM: {gaps}" if gaps else "profile.toml: ok")
    for name, mod in REGISTRY.items():
        on = settings["sources"].get(name)
        need = [k for k in getattr(mod, "NEEDS", ()) if not settings.secret(k)]
        covered = getattr(mod, "COUNTRIES", None)
        country = settings["search"]["country"].lower()
        state = "off" if not on else (f"ON but missing {', '.join(need)}" if need else
                                      f"on, but it does not cover '{country}' (skipped)" if covered and country not in covered else "on")
        if name == "watchlist":
            state = f"{len(settings['watch'].get('companies') or [])} companies"
        ok &= not (on and need and name != "watchlist")
        print(f"source {name:15} {state}")
    ok &= _check_llm(settings)
    from .tailor import find_soffice
    print(f"pdf export: {'LibreOffice found' if find_soffice() else 'LibreOffice not found, DOCX only'}")
    print(f"gmail: {'on' if settings['gmail'].get('enabled') else 'off'}")
    return 0 if ok else 1


def llm_status(settings: Settings) -> tuple[bool, str]:
    from .llm import LLM
    prov = settings["llm"]["provider"]
    if prov == "builtin":
        from . import builtin
        st = builtin.status(settings["llm"].get("model") or "standard")
        label = builtin.MODELS[st["model"]]["label"]
        if st["ready"]:
            return True, f"built-in AI ({label}), downloaded and ready"
        return False, "the built-in AI is not downloaded yet. Open Settings, AI model, and press Download."
    try:
        llm = LLM(settings)
    except RuntimeError as e:
        return False, f"{prov}: {e}"
    if not llm.local:
        return True, (f"{prov} ({llm.model})" if llm.enabled else "none: keyword scoring and template letters")
    try:
        models = llm.list_models()
    except Exception as e:
        start = "Start the Ollama app (or run: ollama serve)" if prov == "ollama" else "Start the model server"
        return False, f"nothing answers at {llm.base_url}. {start}, then test again. ({e.__class__.__name__})"
    have = any(m == llm.model or m.split(":")[0] == llm.model or m.endswith("/" + llm.model) for m in models)
    if have or (len(models) == 1 and prov != "ollama"):
        return True, f"{prov} at {llm.base_url}, model {llm.model} ready"
    hint = f" Run: ollama pull {llm.model}" if prov == "ollama" else ""
    return False, f"{prov} is running, but model '{llm.model}' is not installed. Available: {', '.join(models[:8]) or 'none'}.{hint}"


def _check_llm(settings: Settings) -> bool:
    ok, msg = llm_status(settings)
    print(f"llm: {msg}" if ok else f"llm: PROBLEM: {msg}")
    return ok


def setup_checks(settings: Settings) -> list[dict]:
    """The same checks as `stellenpilot doctor`, as data for the dashboard's setup guide."""
    from .sources import REGISTRY
    from .tailor import find_soffice
    out = []
    name = settings.profile.get("person", {}).get("name") if settings.profile else ""
    from .score import profile_gaps
    gaps = profile_gaps(settings.profile) if name and name != "Alex Example" else ""
    out.append({"step": "cv", "ok": bool(name) and name != "Alex Example" and not gaps,
                "text": gaps or (f"CV saved for {name}" if name and name != "Alex Example" else "Your CV is not saved yet")})
    out.append({"step": "search", "ok": bool(settings["search"]["keywords"]),
                "text": f"Looking for {', '.join(settings['search']['keywords'][:3])} near {settings['search']['city']}"})
    ok, msg = llm_status(settings)
    out.append({"step": "ai", "ok": ok, "text": "AI model: " + msg})
    on = [n for n, m in REGISTRY.items() if n != "watchlist" and settings["sources"].get(n)]
    for n in on:
        need = [k for k in getattr(REGISTRY[n], "NEEDS", ()) if not settings.secret(k)]
        if need:
            out.append({"step": "sources", "ok": False, "text": f"{REGISTRY[n].LABEL} is on but its key is missing"})
    out.append({"step": "sources", "ok": bool(on), "text": f"{len(on)} job source{'s' if len(on) != 1 else ''} on" if on else "No job source is switched on"})
    out.append({"step": "extra", "ok": True, "optional": True,
                "text": "PDF export: LibreOffice found" if find_soffice() else "No LibreOffice, so you get Word files only (optional)"})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="stellenpilot", description="Stellenpilot: your local job search assistant")
    ap.add_argument("--home", type=Path, default=Path.cwd(), help="folder with config.toml and profile.toml")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create config.toml, profile.toml and .env from the examples")
    sub.add_parser("doctor", help="check your setup")
    r = sub.add_parser("run", help="search, score, tailor and sync once")
    r.add_argument("--no-tailor", action="store_true", help="skip CV and letter generation")
    s = sub.add_parser("serve", help="open the local dashboard")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true", help="do not open the browser")
    s.add_argument("--host", default=os.environ.get("JOBHUNT_HOST", "127.0.0.1"),
                   help="address to listen on; keep 127.0.0.1 unless you run inside Docker")
    sub.add_parser("shortcut", help="put a Stellenpilot icon on the desktop that starts this workspace")
    sub.add_parser("gmail", help="sync statuses from Gmail once")
    sub.add_parser("demo", help="load fictional sample jobs to try the dashboard without any keys")
    sub.add_parser("notify-test", help="send a test digest by email or Telegram")
    sub.add_parser("telegram-id", help="show your Telegram chat id after you messaged your bot")
    im = sub.add_parser("import", help="turn your existing CV (PDF, DOCX, TXT) into profile.imported.toml")
    im.add_argument("cv", type=Path)
    ad = sub.add_parser("add", help="add a job yourself, from a link or pasted text")
    ad.add_argument("url", nargs="?", default="", help="link to the ad on a company careers page")
    ad.add_argument("--text", help="ad text, or a path to a .txt file, or - to read from stdin")
    ad.add_argument("--title", default="")
    ad.add_argument("--company", default="")
    ad.add_argument("--location", default="")
    ad.add_argument("--tailor", action="store_true", help="also make the CV and cover letter now")
    ev = sub.add_parser("eval", help="measure how well scoring ranks the jobs you labeled",
                        description="Compare the stored score, keyword scoring and AI models against your labels: "
                                    "thumbs up and down and interviews from the dashboard, or a CSV you fill in.")
    ev.add_argument("--labels", type=Path, help="CSV with columns id and label (0/1 or a grade like 0 to 3)")
    ev.add_argument("--make-sheet", nargs="?", const=100, type=int, metavar="N",
                    help="write eval/labels.csv with N jobs (default 100) spread over all scores, to label by hand")
    ev.add_argument("--provider", action="append", default=[], metavar="NAME[:MODEL]",
                    help="also score with this AI, e.g. builtin:light, ollama:qwen3.5:4b, anthropic. Repeatable.")
    ev.add_argument("--no-llm", action="store_true", help="skip the AI from config.toml (stored and keyword scores only)")
    ev.add_argument("--include-rejected", action="store_true", help="count rejections as bad matches")
    ev.add_argument("--limit", type=int, default=0, help="score at most this many labeled jobs (saves time and API cost)")
    ev.add_argument("--k", type=int, default=10, help="k for precision at k (default 10)")
    w = sub.add_parser("watch", help="find the watchlist entry for a company's careers page")
    w.add_argument("url", help="careers page or job link, or an entry like greenhouse:trivago")
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
        serve(settings, a.port, a.host, open_browser=not a.no_browser)
        return 0
    if a.cmd == "shortcut":
        from .shortcut import create
        print(f"Created {create(settings.home)}. Double click it to start Stellenpilot.")
        return 0
    if a.cmd == "gmail":
        from .db import DB
        from .gmail_sync import sync
        changes = sync(DB(settings.db_path), home, settings["gmail"].get("lookback_days", 3))
        print(f"{len(changes)} status changes")
        return 0
    if a.cmd == "notify-test":
        from .db import DB, today
        from .notify import send_digest
        if not (settings["notify"].get("email") or settings["notify"].get("telegram")):
            print("Turn on email or telegram under [notify] in config.toml first.")
            return 1
        cfg = dict(settings["notify"], only_when_new=False)
        settings.cfg["notify"] = cfg
        problems = send_digest(settings, DB(settings.db_path), {"new": 0, "shortlisted": 0, "problems": ["(test message)"]}, today())
        print("\n".join(problems) if problems else "Sent. Check your inbox or Telegram.")
        return 1 if problems else 0
    if a.cmd == "telegram-id":
        from .notify import telegram_chat_ids
        token = settings.secret("TELEGRAM_BOT_TOKEN")
        if not token:
            print("Put TELEGRAM_BOT_TOKEN in .env first (from @BotFather).")
            return 1
        ids = telegram_chat_ids(token)
        if not ids:
            print("No messages yet. Send any message (e.g. /start) to your bot in Telegram, then run this again.")
            return 1
        for cid, who in ids:
            print(f"TELEGRAM_CHAT_ID={cid}    ({who})")
        return 0
    if a.cmd == "import":
        from .importer import import_cv
        try:
            out, notes = import_cv(a.cv, settings)
        except FileNotFoundError as e:
            print(f"Import failed: {e}")
            return 1
        except (RuntimeError, ValueError) as e:
            print(f"Import failed: {e}")
            return 1
        except OSError as e:  # network: the AI model server is not running or not reachable
            print(f"Import failed: could not reach the AI model ({e}). Is it running? Check with: stellenpilot doctor")
            return 1
        except Exception as e:  # never show a raw traceback for a bad file or odd model output
            print(f"Import failed: {e.__class__.__name__}: {e}")
            return 1
        print(f"Wrote {out.name}. Review it, then rename it to profile.toml.")
        for n in notes[:12]:
            print(f"  check: {n}")
        if len(notes) > 12:
            print(f"  ... {len(notes) - 12} more notes in the file")
        return 0
    if a.cmd == "add":
        from .db import DB
        from .manual import AddError, add_job
        text = a.text or ""
        if text == "-":
            text = sys.stdin.read()
        elif text and len(text) < 260 and "\n" not in text and Path(text).is_file():
            text = Path(text).read_text(encoding="utf-8", errors="replace")
        try:
            res = add_job(settings, DB(settings.db_path), tailor=a.tailor, url=a.url, text=text,
                          title=a.title, company=a.company, location=a.location)
        except AddError as e:
            print(f"Not added: {e}")
            return 1
        except Exception as e:  # never a raw traceback for an odd page or a model hiccup
            print(f"Not added: {e.__class__.__name__}: {e}")
            return 1
        j = res["job"]
        if res["status"] == "exists":
            print(f"Already on your board: {j['title']} at {j['company']} (match {j['match']})")
            return 0
        print(f"Added: {j['title']} at {j['company']}, match {j['match']} ({j['fit']}). {j['why']}")
        if j.get("german_level"):
            print(f"  German asked for: {j['german_level']}")
        if res.get("tailored"):
            print(f"  Documents: {res['tailored']['folder']}")
        return 0
    if a.cmd == "watch":
        from .sources.watchlist import fetch_company, parse_careers_url, title_matches, title_rules
        entry = a.url if ":" in a.url and "//" not in a.url else parse_careers_url(a.url)
        if not entry:
            print("Could not recognize that link. Supported: Greenhouse, Lever, Ashby, Personio, SmartRecruiters.\n"
                  "Tip: open a job on the company's careers page and use the link of its Apply page.")
            return 1
        try:
            jobs = fetch_company(entry, settings["search"]["country"])
        except Exception as e:
            print(f"{entry}: could not read the feed ({e})")
            return 1
        rules = title_rules(settings)
        hits = [j for j in jobs if title_matches(j["title"], rules)]
        print(f"{entry}: {len(jobs)} open jobs, {len(hits)} match your keywords ({' or '.join(' + '.join(r) for r in rules)})")
        for j in hits[:8]:
            print(f"  * {j['title']}  ({j['location']})")
        print(f'\nAdd this to [watch] companies in config.toml:  "{entry}"')
        return 0
    if a.cmd == "eval":
        from .evaluate import default_out_dir, evaluate, format_report, make_sheet
        from .db import DB
        if a.make_sheet is not None:
            path = home / "eval" / "labels.csv"
            if path.exists():
                print(f"{path} already exists. Rename or delete it first, so your labels are not overwritten.")
                return 1
            db = DB(settings.db_path)
            n = make_sheet(db, path, a.make_sheet)
            db.conn.close()
            if not n:
                path.unlink(missing_ok=True)
                print("No scored jobs with an ad text yet. Run a search first: stellenpilot run")
                return 1
            print(f"Wrote {n} jobs to {path}. Put 1 (good match for you) or 0 (not) in the label column, "
                  f"or a grade from 0 to 3. Then run: stellenpilot eval --labels {path}")
            return 0
        def progress(name, i, n):
            if name not in ("stored", "keyword") and (i == 1 or i % 5 == 0 or i == n):
                print(f"  {name}: {i} of {n}", file=sys.stderr, flush=True)
        try:
            report = evaluate(settings, labels_csv=a.labels, providers=a.provider, use_config_llm=not a.no_llm,
                              include_rejected=a.include_rejected, limit=a.limit, k=a.k,
                              out_dir=default_out_dir(home), progress=progress)
        except (ValueError, RuntimeError, OSError) as e:
            print(f"Eval failed: {e}")
            return 1
        print(format_report(report))
        return 0
    if a.cmd == "demo":
        from .demo import load_demo
        n = load_demo(settings)
        print(f"Loaded {n} fictional jobs into {settings.db_path.name}. Now run: stellenpilot serve")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
