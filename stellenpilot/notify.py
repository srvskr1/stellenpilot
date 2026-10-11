"""Daily digest after each run, sent to YOU only: by email (SMTP) or Telegram.

Never sends anything to companies. Secrets live in .env:
  email:    SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, DIGEST_TO (defaults to SMTP_USER)
  telegram: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from datetime import datetime

from .http import HttpError, request_json

TELEGRAM_LIMIT = 4096


def _local_time(iso: str) -> str:
    """Interview times are stored in UTC; show them in this computer's time zone."""
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso[:16].replace("T", " ")


def build_digest(db, result: dict, today: str) -> str:
    new = db.jobs("found_at = ? AND status != 'skipped'", (today,))
    ready = db.jobs("status = 'ready' AND closed = 0")
    interviews = db.jobs("status = 'interview'")
    lines = [f"Job hunt for {today}: {result.get('new', 0)} new jobs, {result.get('shortlisted', 0)} shortlisted."]
    if new:
        lines.append("\nTop new matches:")
        for j in new[:5]:
            where = j["location"] or ("Remote" if j["remote"] else "")
            lines.append(f"* {j['match']}  {j['title']} at {j['company']}" + (f" ({where})" if where else "") + f"\n  {j['url']}")
    if ready:
        lines.append(f"\nReady to apply ({len(ready)}): " + ", ".join(f"{j['company']}" for j in ready[:8]))
    if interviews:
        lines.append("\nInterviews: " + ", ".join(j["company"] + (f" on {_local_time(j['interview_at'])}" if j.get("interview_at") else "") for j in interviews))
    if result.get("gmail"):
        lines.append("\nStatus changes from Gmail: " + ", ".join(f"{c['company']} to {c['to']}" for c in result["gmail"]))
    if result.get("problems"):
        lines.append("\nProblems: " + "; ".join(result["problems"][:5]))
    lines.append("\nOpen your board: stellenpilot serve, then http://127.0.0.1:8765")
    return "\n".join(lines)


def send_email(settings, subject: str, body: str) -> None:
    host, user, pw = settings.secret("SMTP_HOST"), settings.secret("SMTP_USER"), settings.secret("SMTP_PASSWORD")
    if not (host and user and pw):
        raise RuntimeError("email digest needs SMTP_HOST, SMTP_USER and SMTP_PASSWORD in .env")
    port = int(settings.secret("SMTP_PORT") or 587)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, settings.secret("DIGEST_TO") or user
    msg.set_content(body)
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(user, pw)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(user, pw)
            s.send_message(msg)


def send_telegram(settings, body: str) -> None:
    token, chat = settings.secret("TELEGRAM_BOT_TOKEN"), settings.secret("TELEGRAM_CHAT_ID")
    if not (token and chat):
        raise RuntimeError("telegram digest needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
    # Telegram counts UTF-16 code units, so emoji and some symbols count double.
    while len(body.encode("utf-16-le")) // 2 > TELEGRAM_LIMIT:
        body = body[:-200].rstrip() + "\n... (shortened)"
    try:
        data = request_json(f"https://api.telegram.org/bot{token}/sendMessage", method="POST",
                            body={"chat_id": chat, "text": body, "link_preview_options": {"is_disabled": True}})
    except HttpError as e:
        hint = {401: "the bot token is wrong; copy it again from @BotFather",
                400: "the chat id is wrong, or you have not messaged your bot yet; run stellenpilot telegram-id",
                403: "the bot cannot write to you; open your bot in Telegram and press Start"}.get(e.status, str(e))
        raise RuntimeError(f"telegram: {hint}") from None
    if not data.get("ok"):
        raise RuntimeError(f"telegram: {data.get('description', 'unknown error')}")


def telegram_chat_ids(token: str) -> list[tuple[str, str]]:
    """After you message your bot once, this shows your chat id (getUpdates)."""
    data = request_json(f"https://api.telegram.org/bot{token}/getUpdates")
    seen = {}
    for u in data.get("result", []):
        chat = (u.get("message") or u.get("channel_post") or {}).get("chat") or {}
        if chat.get("id"):
            seen[str(chat["id"])] = chat.get("username") or chat.get("title") or chat.get("first_name") or ""
    return list(seen.items())


def send_digest(settings, db, result: dict, today: str) -> list[str]:
    """Send through every enabled channel. Returns problems (empty when all worked)."""
    cfg = settings["notify"]
    if not (cfg.get("email") or cfg.get("telegram")):
        return []
    if cfg.get("only_when_new") and not result.get("new") and not result.get("gmail"):
        return []
    body = build_digest(db, result, today)
    problems = []
    for channel, fn in (("email", lambda: send_email(settings, f"Job hunt {today}: {result.get('new', 0)} new", body)),
                        ("telegram", lambda: send_telegram(settings, body))):
        if cfg.get(channel):
            try:
                fn()
            except Exception as e:
                problems.append(f"{channel} digest: {e}")
    return problems
