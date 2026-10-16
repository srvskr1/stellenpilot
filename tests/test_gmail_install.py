"""Issue #19: the Google packages are installed from the command line, never by the dashboard server."""
import io
import sys
import tempfile
import unittest
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from stellenpilot import gmail_sync
from stellenpilot.cli import main
from stellenpilot.config import Settings


class InstallCommandTests(unittest.TestCase):
    def test_installs_into_this_python_with_pip(self):
        with mock.patch.object(gmail_sync, "packages_installed", return_value=False), \
                mock.patch("stellenpilot.launch.frozen", return_value=False), \
                mock.patch("subprocess.call", return_value=0) as call, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(gmail_sync.install_packages(), 0)
        call.assert_called_once_with([sys.executable, "-m", "pip", "install", *gmail_sync.PACKAGES])
        self.assertIn("Check again", out.getvalue())

    def test_failure_explains_read_only_python(self):
        with mock.patch.object(gmail_sync, "packages_installed", return_value=False), \
                mock.patch("stellenpilot.launch.frozen", return_value=False), \
                mock.patch("subprocess.call", return_value=1), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(gmail_sync.install_packages(), 1)
        self.assertIn("virtual environment", out.getvalue())

    def test_app_build_and_existing_install_run_nothing(self):
        for frozen, have in ((True, False), (False, True)):
            with mock.patch.object(gmail_sync, "packages_installed", return_value=have), \
                    mock.patch("stellenpilot.launch.frozen", return_value=frozen), \
                    mock.patch("subprocess.call") as call, redirect_stdout(io.StringIO()):
                self.assertEqual(gmail_sync.install_packages(), 0)
            call.assert_not_called()

    def test_cli_flag_needs_no_config(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(gmail_sync, "install_packages", return_value=0) as inst:
            self.assertEqual(main(["--home", d, "gmail", "--install"]), 0)
            inst.assert_called_once()
            self.assertFalse((Path(d) / "config.toml").exists())

    def test_pyproject_extra_matches(self):
        import tomllib
        root = Path(__file__).resolve().parents[1]
        extra = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"]["gmail"]
        self.assertEqual(extra, gmail_sync.PACKAGES)


class EndpointTests(unittest.TestCase):
    def test_server_no_longer_installs_and_shows_the_command(self):
        from helpers import fetch_json, http_error, running
        from stellenpilot.server import make_handler
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d, running(make_handler(Settings(Path(d)))) as srv:
            req = urllib.request.Request(f"{srv.base}/api/gmail/install", data=b"{}", method="POST",
                                         headers={"X-Jobhunt": "1", "Content-Type": "application/json"})
            with mock.patch("subprocess.run") as run, mock.patch("subprocess.call") as call:
                self.assertEqual(http_error(req)[0], 404)
                run.assert_not_called()
                call.assert_not_called()
            g = fetch_json(f"{srv.base}/api/settings")["gmail"]
            self.assertEqual(g["installCommand"], "stellenpilot gmail --install")
            self.assertIn("-m stellenpilot gmail --install", g["installCommandFull"])

if __name__ == "__main__":
    unittest.main()
