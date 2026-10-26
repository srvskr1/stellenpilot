"""Update check: offers the right download for a newer release. No real network: GitHub is faked."""
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from stellenpilot import update

PAGE = "https://github.com/srvskr1/stellenpilot/releases/tag/v0.12.0"
DL = "https://github.com/srvskr1/stellenpilot/releases/download/v0.12.0/"


def release(tag="v0.12.0", page=PAGE, base=DL, version="0.12.0"):
    names = [f"Stellenpilot-Setup-{version}.exe", f"Stellenpilot-{version}-mac.dmg", f"Stellenpilot-Portable-{version}.zip"]
    return lambda: {"tag_name": tag, "html_url": page,
                    "assets": [{"name": n, "browser_download_url": base + n} for n in names]}


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.home = Path(self.d.name)

    def tearDown(self):
        self.d.cleanup()

    def status(self, plat="windows", **kw):
        with mock.patch.object(update, "platform", return_value=plat):
            return update.status(self.home, current="0.11.1", **{"now": 1, **kw})

    def test_newer_release_offers_the_installer_for_this_computer(self):
        win = self.status("windows", fetch=release())
        self.assertEqual((win["available"], win["latest"], win["download"]), (True, "0.12.0", DL + "Stellenpilot-Setup-0.12.0.exe"))
        (self.home / update.CACHE).unlink()
        mac = self.status("mac", fetch=release())
        self.assertEqual(mac["download"], DL + "Stellenpilot-0.12.0-mac.dmg")

    def test_linux_gets_the_release_page(self):
        self.assertEqual(self.status("other", fetch=release())["download"], PAGE)

    def test_github_is_asked_at_most_once_a_day(self):
        fetch = mock.Mock(side_effect=release())
        self.status(fetch=fetch, now=1000)
        self.status(fetch=fetch, now=1000 + 3600)
        self.assertEqual(fetch.call_count, 1)

    def test_same_or_older_version_is_not_offered(self):
        for tag in ("v0.11.1", "v0.10.0", "not-a-version"):
            with self.subTest(tag=tag):
                (self.home / update.CACHE).unlink(missing_ok=True)
                self.assertFalse(self.status(fetch=release(tag=tag))["available"])

    def test_switched_off_or_dev_checkout_never_asks(self):
        fetch = mock.Mock(side_effect=AssertionError("must not ask GitHub"))
        self.assertFalse(update.status(self.home, enabled=False, current="0.11.1", fetch=fetch)["available"])
        self.assertFalse(update.status(self.home, current="dev", fetch=fetch)["available"])

    def test_offline_keeps_what_it_knew(self):
        self.status(fetch=release(), now=1)
        s = self.status(fetch=mock.Mock(side_effect=OSError("offline")), now=1 + 2 * 86400)
        self.assertTrue(s["available"])

    def test_links_outside_the_repository_are_never_offered(self):
        s = self.status(fetch=release(page="https://evil.example/", base="https://evil.example/"))
        self.assertTrue(s["download"].startswith(update.PAGE_PREFIX))
        self.assertTrue(s["page"].startswith(update.PAGE_PREFIX))

    def test_installer_of_another_version_is_ignored(self):
        self.assertEqual(update._downloads(release(version="0.11.9")(), "0.12.0"), {})

    def test_pip_install_also_gets_the_command(self):
        with mock.patch("stellenpilot.launch.frozen", return_value=False):
            s = self.status(fetch=release())
        self.assertIn("pip install -U stellenpilot", s["command"])

    def test_homebrew_install_gets_brew_upgrade(self):
        with mock.patch("stellenpilot.launch.frozen", return_value=False), \
             mock.patch.object(update, "homebrew", return_value=True):
            s = self.status(plat="mac", fetch=release())
        self.assertEqual(s["command"], "brew upgrade stellenpilot")

    def test_homebrew_is_told_apart_by_its_cellar_path(self):
        self.assertTrue(update.homebrew("/opt/homebrew/Cellar/stellenpilot/0.12.0/libexec"))
        self.assertTrue(update.homebrew("/usr/local/Cellar/stellenpilot/0.12.0/libexec"))
        self.assertFalse(update.homebrew("/Users/me/stellenpilot-env"))
        self.assertFalse(update.homebrew("/opt/homebrew/Cellar/python@3.13/3.13.1/Frameworks"))

    def test_app_gets_no_command(self):
        with mock.patch("stellenpilot.launch.frozen", return_value=True):
            self.assertNotIn("command", self.status(fetch=release()))


class RouteTests(unittest.TestCase):
    def test_update_route_answers_and_nothing_can_install(self):
        from helpers import fetch_json, http_error, running
        from stellenpilot.config import Settings
        from stellenpilot.server import make_handler
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            settings = Settings(Path(d))
            settings["ui"]["check_updates"] = False  # no network in tests
            with running(make_handler(settings)) as srv:
                self.assertFalse(fetch_json(f"{srv.base}/api/update")["available"])
                req = urllib.request.Request(f"{srv.base}/api/update/install", data=b"{}", method="POST",
                                             headers={"X-Jobhunt": "1", "Content-Type": "application/json"})
                self.assertEqual(http_error(req)[0], 404)  # there is no install route at all


if __name__ == "__main__":
    unittest.main()


class HomebrewPathTests(unittest.TestCase):
    """The daily task and desktop icon must keep working after `brew upgrade` removes the old version."""

    def test_cellar_path_becomes_the_stable_opt_link(self):
        from stellenpilot.launch import python
        self.assertEqual(python("/opt/homebrew/Cellar/stellenpilot/0.12.0/libexec/bin/python"),
                         "/opt/homebrew/opt/stellenpilot/libexec/bin/python")
        self.assertEqual(python("/usr/local/Cellar/stellenpilot/0.12.0_1/libexec/bin/python3.13"),
                         "/usr/local/opt/stellenpilot/libexec/bin/python3.13")

    def test_other_pythons_are_left_alone(self):
        from stellenpilot.launch import python
        for exe in ("/Users/me/stellenpilot-env/bin/python", r"C:\Python313\python.exe",
                    "/opt/homebrew/Cellar/python@3.13/3.13.1/bin/python3.13"):
            self.assertEqual(python(exe), exe)
