"""Optional Gmail status sync. Read only (gmail.readonly scope), never sends or changes mail.

Setup (docs/gmail.md): create your own Google Cloud project and OAuth client, save it as
credentials.json next to config.toml, then run `jobhunt gmail`. A browser window asks for
consent once; the token is stored in token.json (ignored by git). Apps in Google's Testing
mode need re-consent about every 7 days.
"""
from __future__ import annotations

import re
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
RANK = {"new": 0, "ready": 1, "skipped": 1, "applied": 2, "interview": 3, "offer": 4, "rejected": 5}
RX = {
    "offer": re.compile(r"(job offer|offer letter|we are pleased to offer|vertragsangebot|arbeitsvertrag|zusage)", re.I),
    "rejected": re.compile(r"(leider|absage|unfortunately|not be considered|nicht ber(ü|ue)cksichtig|other candidates|anderen? kandidat|decided not to|not to move forward|nicht f(ü|ue)r (dich|sie) entschieden|regret to inform)", re.I),
    "interview": re.compile(r"(invite you to (an |a )?(interview|call|conversation)|einladung zu(m)? |vorstellungsgespr(ä|ae)ch|kennenlern|schedule (an |a )?(interview|call)|interview invitation|coding challenge|take.?home|case study)", re.I),
    "applied": re.compile(r"(received your application|application (was )?received|eingegangen|thank you for (your )?appl|thank you for applying|vielen dank f(ü|ue)r (ihre|deine) bewerbung|danke f(ü|ue)r (ihre|deine) bewerbung|application was sent)", re.I),
}
QUERY = ('(subject:(application OR Bewerbung OR interview OR "Vorstellungsgespräch" OR offer OR Absage) '
         'OR "your application" OR "deine Bewerbung" OR "Ihre Bewerbung")')


def classify(text: str) -> str | None:
    for status in ("offer", "rejected", "interview", "applied"):
        if RX[status].search(text):
            return status
    return None


def company_key(name: str) -> str | None:
    words = re.sub(r"[^a-z0-9äöüß ]", " ", (name or "").lower()).split()
    words = [w for w in words if len(w) >= 3 and w not in {"gmbh", "group", "the", "und", "and", "se", "ag", "mbh"}]
    return words[0] if words else None


def _service(home: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError("Gmail sync needs extra packages: pip install 'job-hunt-pipeline[gmail]'") from e
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
        token.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def sync(db, home: Path, lookback_days: int = 3) -> list[dict]:
    """Move job statuses forward based on recent mail. Never moves a status backwards."""
    svc = _service(home)
    q = f"newer_than:{lookback_days}d {QUERY}"
    threads = svc.users().threads().list(userId="me", q=q, maxResults=50).execute().get("threads", [])
    jobs = [(j, company_key(j["company"])) for j in db.jobs()]
    changes = []
    for th in threads:
        full = svc.users().threads().get(userId="me", id=th["id"], format="metadata",
                                         metadataHeaders=["From", "Subject", "Date"]).execute()
        last = full["messages"][-1]
        hdr = {h["name"]: h["value"] for h in last["payload"].get("headers", [])}
        text = " ".join([hdr.get("From", ""), hdr.get("Subject", ""), last.get("snippet", "")])
        status = classify(text)
        if not status:
            continue
        low = text.lower()
        hit = next((j for j, k in jobs if k and k in low), None)
        if not hit or hit["status"] in ("rejected", "offer"):
            continue
        if RANK[status] <= RANK.get(hit["status"], 0):
            continue
        note = {"applied": "Receipt confirmed", "interview": "Interview invitation",
                "rejected": "Rejection email", "offer": "Offer email"}[status]
        db.set_status(hit["id"], status, source="gmail", note=f"{note}: {hdr.get('Subject', '')[:80]}")
        changes.append({"id": hit["id"], "company": hit["company"], "from": hit["status"], "to": status})
    return changes
