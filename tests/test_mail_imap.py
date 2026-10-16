"""Reading application emails with an app password over IMAP (server faked; nothing leaves this computer)."""
import email.message
import imaplib
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from stellenpilot import mail_imap
from stellenpilot.config import Settings
from stellenpilot.db import DB
from stellenpilot.gmail_sync import sync


def _mail(sender, subject, body, html=False):
    m = email.message.EmailMessage()
    m["From"], m["Subject"] = sender, subject
    m.set_content(body, subtype="html" if html else "plain")
    return m.as_bytes()


MAILS = [
    _mail("Talent Team <jobs@nordlicht-energy.de>", "Ihre Bewerbung", "Vielen Dank für Ihre Bewerbung als Werkstudent."),
    _mail("Rhein Mobility <careers@rheinmobility.com>", "Your application",
          "<p>Unfortunately, we decided not to move forward with your application.</p>", html=True),
    _mail("LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>", "30 new jobs for you", "Nordlicht Energy is hiring"),
]


class FakeIMAP:
    """Records what Stellenpilot asks the server, to prove it only reads."""
    instances = []
    password = "abcdefghijklmnop"

    def __init__(self, host, port, ssl_context=None, timeout=None):
        self.host, self.calls = host, []
        FakeIMAP.instances.append(self)

    def login(self, user, password):
        self.calls.append(("login", user))
        if password != FakeIMAP.password:
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials (Failure)")
        return "OK", [b"ok"]

    def select(self, box, readonly=False):
        self.calls.append(("select", box, readonly))
        return "OK", [b"3"]

    def search(self, charset, *criteria):
        self.calls.append(("search",) + criteria)
        return "OK", [b"1 2 3"]

    def fetch(self, ids, what):
        self.calls.append(("fetch", what))
        if what == "(RFC822.SIZE)":
            return "OK", [f"{i} (RFC822.SIZE {len(MAILS[i - 1])})".encode() for i in (1, 2, 3)]
        i = int(ids)
        return "OK", [(f"{i} (BODY[] {{{len(MAILS[i - 1])}}}".encode(), MAILS[i - 1]), b")"]

    def logout(self):
        self.calls.append(("logout",))


JOBS = [{"id": "a", "source": "T", "title": "Werkstudent Data", "company": "Nordlicht Energy GmbH", "status": "ready", "dedupe_key": "a"},
        {"id": "b", "source": "T", "title": "Data Analyst", "company": "Rhein Mobility AG", "status": "applied", "dedupe_key": "b"}]


@mock.patch.dict(os.environ)
class ImapTests(unittest.TestCase):
    def setUp(self):
        FakeIMAP.instances.clear()
        self.patch = mock.patch.object(mail_imap.imaplib, "IMAP4_SSL", FakeIMAP)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_hosts(self):
        self.assertEqual(mail_imap.host_for("me@gmail.com"), "imap.gmail.com")
        self.assertEqual(mail_imap.host_for("me@web.de"), "imap.web.de")
        self.assertEqual(mail_imap.host_for("me@uni.de", "imap.uni.de"), "imap.uni.de")
        with self.assertRaisesRegex(mail_imap.MailError, "Mail server"):
            mail_imap.host_for("me@unknown-provider.de")
        with self.assertRaisesRegex(mail_imap.MailError, "Outlook"):
            mail_imap.host_for("me@outlook.com")

    def test_read_only_and_peek(self):
        msgs = mail_imap.fetch("imap.gmail.com", "me@gmail.com", "abcd efgh ijkl mnop", 3)  # spaces as Google shows it
        calls = FakeIMAP.instances[0].calls
        self.assertIn(("select", "INBOX", True), calls)  # EXAMINE, never SELECT read write
        self.assertTrue(all(c[1] in ("(RFC822.SIZE)", "(BODY.PEEK[])") for c in calls if c[0] == "fetch"))
        self.assertEqual(calls[-1], ("logout",))
        self.assertEqual(len(msgs), 3)
        self.assertIn("decided not to move forward", msgs[1]["snippet"])  # html turned into text
        self.assertNotIn("<p>", msgs[1]["snippet"])

    def test_wrong_password_is_explained(self):
        with self.assertRaisesRegex(mail_imap.MailError, "app password"):
            mail_imap.check("imap.gmail.com", "me@gmail.com", "my-normal-password")

    def test_sync_moves_statuses(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "config.toml").write_text('[gmail]\nenabled = true\nmethod = "imap"\naddress = "me@gmail.com"\n', encoding="utf-8")
            (home / ".env").write_text(f"{mail_imap.SECRET}={FakeIMAP.password}\n", encoding="utf-8")
            settings = Settings(home)
            db = DB(settings.db_path)
            for j in JOBS:
                db.insert_job(j)
            changes = sync(db, home, 3, settings=settings)
            self.assertEqual({(c["company"], c["to"]) for c in changes},
                             {("Nordlicht Energy GmbH", "applied"), ("Rhein Mobility AG", "rejected")})
            self.assertEqual(db.job("a")["status"], "applied")  # the job alert was ignored
            db.conn.close()

    def test_missing_password_says_what_to_do(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "config.toml").write_text('[gmail]\nenabled = true\nmethod = "imap"\naddress = "me@gmail.com"\n', encoding="utf-8")
            os.environ.pop(mail_imap.SECRET, None)
            db = DB(Path(d) / "x.db")
            try:
                with self.assertRaisesRegex(RuntimeError, "Connect it again"):
                    sync(db, home, 3, settings=Settings(home))
            finally:
                db.conn.close()  # Windows cannot delete an open database file


@mock.patch.dict(os.environ)
class EndpointTests(unittest.TestCase):
    def _req(self, base, path, body):
        return urllib.request.Request(f"{base}{path}", data=json.dumps(body).encode(), method="POST",
                                      headers={"X-Jobhunt": "1", "Content-Type": "application/json"})

    def _post(self, base, path, body):
        from helpers import fetch_json
        return fetch_json(self._req(base, path, body))

    def test_connect_and_disconnect(self):
        from stellenpilot.server import make_handler
        os.environ.pop(mail_imap.SECRET, None)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d, \
                mock.patch.object(mail_imap.imaplib, "IMAP4_SSL", FakeIMAP):
            home = Path(d)
            settings = Settings(home)
            from helpers import http_error, running
            with running(make_handler(settings)) as srv:
                base = srv.base
                code, body = http_error(self._req(base, "/api/gmail/imap", {"address": "me@gmail.com", "password": "wrong"}))
                self.assertIn("app password", body["error"])
                g = self._post(base, "/api/gmail/imap", {"address": "me@gmail.com", "password": "abcd efgh ijkl mnop"})["gmail"]
                self.assertEqual((g["method"], g["address"], g["enabled"], g["connected"]), ("imap", "me@gmail.com", True, True))
                env = (home / ".env").read_text(encoding="utf-8")
                self.assertIn(f"{mail_imap.SECRET}=abcdefghijklmnop", env)  # stored without spaces, in .env only
                self.assertNotIn("abcdefghijklmnop", (home / "config.toml").read_text(encoding="utf-8"))
                if os.name != "nt":
                    self.assertEqual((home / ".env").stat().st_mode & 0o077, 0)
                g = self._post(base, "/api/gmail/disconnect", {})["gmail"]
                self.assertFalse(g["enabled"])
                self.assertNotIn(mail_imap.SECRET, (home / ".env").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
