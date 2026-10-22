"""Update check and the Windows one click install. No real network: GitHub and downloads are faked."""
import hashlib
import io
import json
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from stellenpilot import update

PAGE = "https://github.com/srvskr1/stellenpilot/releases/tag/v0.12.0"
DL = "https://github.com/srvskr1/stellenpilot/releases/download/v0.12.0/Stellenpilot-Setup-0.12.0.exe"
PAYLOAD = b"MZ fake installer"
DIGEST = "sha256:" + hashlib.sha256(PAYLOAD).hexdigest()


def release(tag="v0.12.0", url=DL, digest=DIGEST, page=PAGE, name="Stellenpilot-Setup-0.12.0.exe"):
    return lambda: {"tag_name": tag, "html_url": page,
                    "assets": [{"name": name, "browser_download_url": url, "digest": digest, "size": len(PAYLOAD)}]}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.home = Path(self.d.name)

    def tearDown(self):
        self.d.cleanup()

    def test_newer_release_is_offered_once_a_day(self):
        calls = []
        def fetch():
            calls.append(1)
            return release()()
        with mock.patch.object(update, "kind", return_value="windows"):
            s = update.status(self.home, current="0.11.1", fetch=fetch, now=1000)
            update.status(self.home, current="0.11.1", fetch=fetch, now=1000 + 3600)
        self.assertEqual((s["available"], s["latest"], s["oneClick"], s["page"]), (True, "0.12.0", True, PAGE))
        self.assertEqual(len(calls), 1)  # second check within a day came from the cache

    def test_same_or_older_version_is_not_offered(self):
        for tag in ("v0.11.1", "v0.10.0", "not-a-version"):
            with self.subTest(tag=tag):
                (self.home / update.CACHE).unlink(missing_ok=True)
                self.assertFalse(update.status(self.home, current="0.11.1", fetch=release(tag=tag), now=1)["available"])

    def test_switched_off_or_dev_checkout_never_asks(self):
        fetch = mock.Mock(side_effect=AssertionError("must not ask GitHub"))
        self.assertFalse(update.status(self.home, enabled=False, current="0.11.1", fetch=fetch)["available"])
        self.assertFalse(update.status(self.home, current="dev", fetch=fetch)["available"])

    def test_offline_keeps_what_it_knew(self):
        update.status(self.home, current="0.11.1", fetch=release(), now=1)
        s = update.status(self.home, current="0.11.1", fetch=mock.Mock(side_effect=OSError("offline")), now=1 + 2 * 86400)
        self.assertTrue(s["available"])

    def test_foreign_links_are_never_used(self):
        fetch = release(url="https://evil.example/Stellenpilot-Setup-0.12.0.exe", page="https://evil.example/")
        with mock.patch.object(update, "kind", return_value="windows"):
            s = update.status(self.home, current="0.11.1", fetch=fetch, now=1)
        self.assertFalse(s["oneClick"])  # no verified installer, so no one click install
        self.assertTrue(s["page"].startswith(update.PAGE_PREFIX))

    def test_installer_without_digest_or_for_another_version_is_ignored(self):
        for kw in ({"digest": None}, {"digest": "md5:abc"}, {"name": "Stellenpilot-Setup-0.11.9.exe"}):
            with self.subTest(**kw):
                self.assertIsNone(update._setup_asset(release(**kw)(), "0.12.0"))

    def test_pip_and_docker_get_a_command_not_an_install(self):
        with mock.patch.object(update, "kind", return_value="pip"):
            s = update.status(self.home, current="0.11.1", fetch=release(), now=1)
        self.assertIn("pip install -U stellenpilot", s["command"])
        self.assertFalse(s["oneClick"])


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.dest = Path(self.d.name) / "setup.exe"

    def tearDown(self):
        self.d.cleanup()

    def test_matching_checksum_is_kept(self):
        setup = {"url": DL, "sha256": DIGEST[7:]}
        update.download(setup, self.dest, opener=lambda req, timeout: Resp(PAYLOAD))
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)

    def test_tampered_installer_is_deleted_and_not_run(self):
        setup = {"url": DL, "sha256": DIGEST[7:]}
        with self.assertRaises(ValueError):
            update.download(setup, self.dest, opener=lambda req, timeout: Resp(b"MZ something else"))
        self.assertFalse(self.dest.exists())

    def test_download_from_elsewhere_is_refused_before_connecting(self):
        opener = mock.Mock(side_effect=AssertionError("must not connect"))
        with self.assertRaises(ValueError):
            update.download({"url": "https://evil.example/x.exe", "sha256": DIGEST[7:]}, self.dest, opener=opener)

    def test_oversized_download_stops(self):
        with mock.patch.object(update, "MAX_BYTES", 4), self.assertRaises(ValueError):
            update.download({"url": DL, "sha256": DIGEST[7:]}, self.dest, opener=lambda req, timeout: Resp(PAYLOAD))

    def test_install_only_in_the_windows_app_and_only_upwards(self):
        with tempfile.TemporaryDirectory() as h:
            with mock.patch.object(update, "kind", return_value="pip"), self.assertRaises(ValueError):
                update.install(Path(h), current="0.11.1")
            with mock.patch.object(update, "kind", return_value="windows"), \
                    mock.patch.object(update, "_fetch", release(tag="v0.11.0")), self.assertRaises(ValueError):
                update.install(Path(h), current="0.11.1")

    def test_install_starts_the_verified_installer_silently(self):
        with tempfile.TemporaryDirectory() as h, \
                mock.patch.object(update, "kind", return_value="windows"), \
                mock.patch.object(update, "_fetch", release()), \
                mock.patch.object(update.urllib.request, "urlopen", lambda req, timeout: Resp(PAYLOAD)), \
                mock.patch.object(update.subprocess, "Popen") as popen:
            self.assertEqual(update.install(Path(h), current="0.11.1"), "0.12.0")
        args = popen.call_args[0][0]
        self.assertTrue(args[0].endswith("Stellenpilot-Setup.exe"))
        self.assertIn("/SILENT", args)
        self.assertFalse(popen.call_args[1].get("shell"))


class RouteTests(unittest.TestCase):
    def test_install_route_needs_the_dashboard_header(self):
        from helpers import http_error, running
        from stellenpilot.config import Settings
        from stellenpilot.server import make_handler
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d, running(make_handler(Settings(Path(d)))) as srv:
            req = urllib.request.Request(f"{srv.base}/api/update/install", data=b"{}", method="POST")
            self.assertEqual(http_error(req)[0], 403)
            req = urllib.request.Request(f"{srv.base}/api/update/install", data=b"{}", method="POST",
                                         headers={"X-Jobhunt": "1", "Origin": "https://evil.example"})
            self.assertEqual(http_error(req)[0], 403)
            req = urllib.request.Request(f"{srv.base}/api/update/install", data=b"{}", method="POST",
                                         headers={"X-Jobhunt": "1", "Content-Type": "application/json"})
            code, body = http_error(req)  # not the Windows app, so refused with a reason, nothing runs
            self.assertEqual(code, 400)
            self.assertIn("Windows app", body["error"])


if __name__ == "__main__":
    unittest.main()
