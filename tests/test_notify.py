"""Daily digest building and sending (network mocked)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobradar import notify
from jobradar.config import Settings
from jobradar.db import DB, today


class NotifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        home = Path(self.tmp.name)
        (home / "config.toml").write_text("[notify]\ntelegram = true\nemail = true\n", encoding="utf-8")
        (home / ".env").write_text("TELEGRAM_BOT_TOKEN=t\nTELEGRAM_CHAT_ID=1\nSMTP_HOST=h\nSMTP_USER=u@x.de\nSMTP_PASSWORD=p\n", encoding="utf-8")
        self.settings = Settings(home)
        self.db = DB(self.settings.db_path)
        self.db.insert_job({"id": "a", "source": "S", "title": "Data Analyst", "company": "Acme", "location": "Essen",
                            "url": "https://x", "match": 82, "dedupe_key": "a"})

    def tearDown(self):
        self.tmp.cleanup()

    def test_digest_text(self):
        body = notify.build_digest(self.db, {"new": 1, "shortlisted": 1}, today())
        self.assertIn("82  Data Analyst at Acme (Essen)", body)

    def test_sends_both_channels(self):
        with mock.patch.object(notify, "request_json", return_value={"ok": True}) as tg, \
             mock.patch.object(notify.smtplib, "SMTP") as smtp:
            problems = notify.send_digest(self.settings, self.db, {"new": 1}, today())
        self.assertEqual(problems, [])
        self.assertEqual(tg.call_args.kwargs["body"]["chat_id"], "1")
        smtp.return_value.__enter__.return_value.send_message.assert_called_once()

    def test_long_telegram_message_is_cut(self):
        with mock.patch.object(notify, "request_json", return_value={"ok": True}) as tg:
            notify.send_telegram(self.settings, "x" * 5000)
        self.assertLessEqual(len(tg.call_args.kwargs["body"]["text"]), 4096)

    def test_failures_become_problems_not_crashes(self):
        with mock.patch.object(notify, "request_json", return_value={"ok": False, "description": "Unauthorized"}), \
             mock.patch.object(notify.smtplib, "SMTP", side_effect=OSError("no route")):
            problems = notify.send_digest(self.settings, self.db, {"new": 1}, today())
        self.assertEqual(len(problems), 2)


if __name__ == "__main__":
    unittest.main()
