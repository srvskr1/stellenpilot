"""Optional email status sync. Read only, never sends or changes mail.

Two ways to read (docs/gmail.md):
* method "imap" (the simple one): your address and an app password; see mail_imap.py.
* method "oauth": your own Google Cloud project and OAuth client saved as credentials.json, with
  the gmail.readonly scope. The token is stored in token.json (ignored by git). Apps in Google's
  Testing mode need re-consent about every 7 days.
Both hand the same {"sender", "subject", "snippet"} messages to apply(), which moves statuses.
"""
from __future__ import annotations

import re
from pathlib import Path

from .text import _norm

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
RANK = {"new": 0, "ready": 1, "skipped": 1, "applied": 2, "interview": 3, "offer": 4, "rejected": 5}
RX = {
    "offer": re.compile(r"\b(job offer|offer letter|we are (pleased|happy|delighted) to offer you|vertragsangebot|ihr arbeitsvertrag|zusage f(ü|ue)r)\b(?!s)", re.I),
    "rejected": re.compile(r"\b(leider (müssen|muessen|können|koennen|haben) wir|absage|unfortunately,? we|not be considered|nicht ber(ü|ue)cksichtig|other candidates|anderen? kandidat|decided not to (move|proceed)|not to move forward|nicht f(ü|ue)r (dich|sie) entschieden|regret to inform)\b", re.I),
    "interview": re.compile(r"\b(invite you to (an |a )?(interview|call|conversation)|einladung zu(m)? (vorstellungs|kennenlern|interview|gespr)|vorstellungsgespr(ä|ae)ch|schedule (an |a )?(interview|call)|interview invitation|coding challenge|take.?home (task|assignment))", re.I),
    "applied": re.compile(r"\b(received your application|application (has been |was )?received|bewerbung (ist )?(bei uns )?eingegangen|thank you for (your )?applying|thank you for your application|vielen dank f(ü|ue)r (ihre|deine) bewerbung|danke f(ü|ue)r (ihre|deine) bewerbung|application was sent)", re.I),
}
ALERT = re.compile(r"(job ?alert|jobs? for you|new jobs|jobalerts|newsletter|recommended jobs|stellenangebote f(ü|ue)r sie)", re.I)
QUERY = ('(subject:(application OR Bewerbung OR interview OR "Vorstellungsgespräch" OR offer OR Absage) '
         'OR "your application" OR "deine Bewerbung" OR "Ihre Bewerbung") -in:sent')


def classify(text: str) -> str | None:
    for status in ("offer", "rejected", "interview", "applied"):
        if RX[status].search(text):
            return status
    return None


def _company_matches(company: str, text_norm: str, sender_domain: str) -> bool:
    """Whole normalized company name in the email, or its main word in the sender's domain."""
    name = _norm(company)
    if not name:
        return False
    if re.search(rf"\b{re.escape(name)}\b", text_norm):
        return True
    main = max(name.split(), key=len)
    return len(main) >= 4 and main in sender_domain


def _pick(candidates: list[dict]) -> dict | None:
    """Prefer jobs you are actively pursuing when several match."""
    active = [j for j in candidates if j["status"] in ("applied", "interview", "ready")]
    pool = active or candidates
    return pool[0] if len(pool) == 1 else None  # ambiguous: do nothing


def _service(home: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError('Gmail sync needs extra packages. Inside the stellenpilot folder run: pip install -e ".[gmail]"') from e
    token, creds_file = home / "token.json", home / "credentials.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds or not creds.valid:
            if not creds_file.exists():
                raise RuntimeError("credentials.json not found. See docs/gmail.md")
            creds = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES).run_local_server(port=0)
        from .config import write_private
        write_private(token, creds.to_json())  # gives read access to your mailbox: only you may read it
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _gmail_api_messages(home: Path, lookback_days: int) -> list[dict]:
    svc = _service(home)
    q = f"newer_than:{lookback_days}d {QUERY}"
    threads = svc.users().threads().list(userId="me", q=q, maxResults=50).execute().get("threads", [])
    out = []
    for th in threads:
        full = svc.users().threads().get(userId="me", id=th["id"], format="metadata",
                                         metadataHeaders=["From", "Subject", "Date"]).execute()
        received = [m for m in full.get("messages", []) if "SENT" not in (m.get("labelIds") or [])]
        if not received:
            continue
        last = received[-1]
        hdr = {h["name"]: h["value"] for h in last["payload"].get("headers", [])}
        out.append({"sender": hdr.get("From", ""), "subject": hdr.get("Subject", ""), "snippet": last.get("snippet", "")})
    return out


def apply(db, messages: list[dict]) -> list[dict]:
    """Move job statuses forward based on the messages. Never moves a status backwards."""
    changes = []
    for msg in messages:
        sender, subject = msg.get("sender", ""), msg.get("subject", "")
        if ALERT.search(sender + " " + subject):
            continue
        text = " ".join([sender, subject, msg.get("snippet", "")])
        status = classify(text)
        if not status:
            continue
        domain = (re.search(r"@([\w.-]+)", sender) or [None, ""])[1].lower()
        text_norm = _norm(text)
        hit = _pick([j for j in db.jobs() if _company_matches(j["company"], text_norm, domain)])
        if not hit:
            continue
        current = db.job(hit["id"])["status"]  # fresh read: earlier messages may have changed it
        if current in ("rejected", "offer") or RANK[status] <= RANK.get(current, 0):
            continue
        note = {"applied": "Receipt confirmed", "interview": "Interview invitation",
                "rejected": "Rejection email", "offer": "Offer email"}[status]
        db.set_status(hit["id"], status, source="gmail", note=f"{note}: {subject[:80]}")
        changes.append({"id": hit["id"], "company": hit["company"], "from": current, "to": status})
    return changes


def sync(db, home: Path, lookback_days: int = 3, settings=None) -> list[dict]:
    """Read recent mail the way the person connected it, then move statuses forward."""
    if settings is None:
        from .config import Settings
        settings = Settings(home)
    cfg = settings["gmail"]
    if cfg.get("method") == "imap":
        from . import mail_imap
        password = settings.secret(mail_imap.SECRET)
        if not password or not cfg.get("address"):
            raise RuntimeError("Email is not connected: the address or app password is missing. Connect it again under Settings, Email.")
        messages = mail_imap.fetch(mail_imap.host_for(cfg["address"], cfg.get("imap_host", "")),
                                   cfg["address"], password, lookback_days)
    else:
        messages = _gmail_api_messages(home, lookback_days)
    return apply(db, messages)
