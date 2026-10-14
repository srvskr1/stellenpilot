"""Read application emails over IMAP with an app password. No Google Cloud project needed.

Gmail (and GMX, web.de, Yahoo, t-online, Posteo, mailbox.org) let you create an app password: a
separate password for one program, which you can delete again at any time. Stellenpilot uses it
only to read: the mailbox is opened read only (EXAMINE) and messages are fetched with BODY.PEEK,
so nothing is marked as read, moved, labeled, deleted or sent.

The password lives in .env (readable only by you), never in config.toml.
"""
from __future__ import annotations

import email
import email.header
import email.utils
import html
import imaplib
import re
import socket
import ssl
from datetime import date, timedelta

SECRET = "MAIL_APP_PASSWORD"

# Mail domain to IMAP server. Anything else: the person types the server (their provider's help page has it).
HOSTS = {
    "gmail.com": "imap.gmail.com", "googlemail.com": "imap.gmail.com",
    "gmx.de": "imap.gmx.net", "gmx.net": "imap.gmx.net", "gmx.at": "imap.gmx.net", "gmx.ch": "imap.gmx.net",
    "web.de": "imap.web.de",
    "yahoo.com": "imap.mail.yahoo.com", "yahoo.de": "imap.mail.yahoo.com",
    "t-online.de": "secureimap.t-online.de",
    "posteo.de": "posteo.de", "posteo.net": "posteo.de",
    "mailbox.org": "imap.mailbox.org",
    "icloud.com": "imap.mail.me.com", "me.com": "imap.mail.me.com",
}
# Providers that no longer accept passwords over IMAP for personal accounts.
NO_PASSWORDS = {"outlook.com", "hotmail.com", "hotmail.de", "live.com", "live.de", "msn.com"}

MAX_MESSAGES = 300          # newest first; a few days of mail
MAX_BYTES = 400_000         # skip big newsletters with images
TIMEOUT = 30


class MailError(RuntimeError):
    """A problem the person can fix, in plain words."""


def host_for(address: str, given: str = "") -> str:
    if given.strip():
        return given.strip()
    domain = address.rsplit("@", 1)[-1].lower().strip()
    if domain in NO_PASSWORDS:
        raise MailError("Outlook and Hotmail only allow Microsoft's own sign in for reading mail, which "
                        "Stellenpilot does not support yet. Forward application emails to a Gmail or GMX address "
                        "and connect that one.")
    if domain not in HOSTS:
        raise MailError(f"Stellenpilot does not know the mail server for {domain}. Enter it under Mail server "
                        "(your provider's help pages list it as the IMAP server).")
    return HOSTS[domain]


def _connect(host: str, address: str, password: str) -> imaplib.IMAP4_SSL:
    password = "".join(password.split())  # Google shows app passwords in groups of four with spaces
    try:
        box = imaplib.IMAP4_SSL(host, 993, ssl_context=ssl.create_default_context(), timeout=TIMEOUT)
    except (socket.gaierror, OSError) as e:
        raise MailError(f"Could not reach the mail server {host}. Check the server name and your internet "
                        f"connection. ({e.__class__.__name__})") from None
    try:
        box.login(address, password)
    except imaplib.IMAP4.error as e:
        msg = str(e).lower()
        try:
            box.logout()
        except Exception:
            pass
        if "application-specific" in msg or "app password" in msg or "web login required" in msg:
            raise MailError("Google wants an app password here, not your normal password. Create one under "
                            "Google Account, Security, App passwords, and paste it.") from None
        if "imap" in msg and ("disabled" in msg or "not enabled" in msg):
            raise MailError("IMAP is switched off for this mailbox. Turn on IMAP in your mail settings, then try again.") from None
        raise MailError("The mail server did not accept this address and password. Check the address, and use an "
                        "app password (16 letters for Gmail), not your normal password.") from None
    return box


def check(host: str, address: str, password: str) -> None:
    """Log in and open the inbox read only, then log out. Raises MailError with a plain message."""
    box = _connect(host, address, password)
    try:
        typ, _ = box.select("INBOX", readonly=True)
        if typ != "OK":
            raise MailError("Logged in, but the inbox could not be opened.")
    finally:
        try:
            box.logout()
        except Exception:
            pass


def _header(value) -> str:
    parts = []
    for text, enc in email.header.decode_header(value or ""):
        parts.append(text.decode(enc or "utf-8", "replace") if isinstance(text, bytes) else text)
    return " ".join("".join(parts).split())


def _body_text(msg, limit: int = 1500) -> str:
    """First plain text of the message (or HTML with the tags removed), as a short snippet."""
    best = ""
    for part in msg.walk() if msg.is_multipart() else [msg]:
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html") or part.get_filename():
            continue
        try:
            raw = part.get_payload(decode=True) or b""
            text = raw.decode(part.get_content_charset() or "utf-8", "replace")
        except Exception:
            continue
        if ctype == "text/html":
            text = html.unescape(re.sub(r"(?is)<(script|style)\b.*?</\1>|<[^>]+>", " ", text))
        if ctype == "text/plain" or not best:
            best = text
        if ctype == "text/plain":
            break
    return " ".join(best.split())[:limit]


def fetch(host: str, address: str, password: str, lookback_days: int = 3) -> list[dict]:
    """Recent inbox messages as {"sender", "subject", "snippet"}, newest last. Read only."""
    box = _connect(host, address, password)
    out = []
    try:
        typ, _ = box.select("INBOX", readonly=True)  # EXAMINE: nothing in the mailbox can change
        if typ != "OK":
            raise MailError("Logged in, but the inbox could not be opened.")
        since = (date.today() - timedelta(days=max(1, int(lookback_days)))).strftime("%d-%b-%Y")
        typ, data = box.search(None, "SINCE", since)
        ids = (data[0] or b"").split()[-MAX_MESSAGES:] if typ == "OK" else []
        if not ids:
            return []
        typ, sizes = box.fetch(b",".join(ids), "(RFC822.SIZE)")
        small = []
        for line in sizes or []:
            m = re.match(rb"(\d+) \(RFC822\.SIZE (\d+)\)", line if isinstance(line, bytes) else b"")
            if m and int(m.group(2)) <= MAX_BYTES:
                small.append(m.group(1))
        for mid in small:
            typ, data = box.fetch(mid, "(BODY.PEEK[])")  # PEEK: the message stays unread
            raw = next((p[1] for p in data or [] if isinstance(p, tuple)), None)
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            out.append({"sender": _header(msg.get("From")), "subject": _header(msg.get("Subject")),
                        "snippet": _body_text(msg)})
    finally:
        try:
            box.logout()
        except Exception:
            pass
    return out
