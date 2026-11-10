import sys
import unittest
from pathlib import Path
from unittest import mock

from stellenpilot import app, launch


class AppTest(unittest.TestCase):
    def test_arguments_decide_app_or_command_line(self):
        self.assertEqual(app._app_mode([]), app.default_home())
        self.assertEqual(app._app_mode(["--home", "X"]), Path("X"))
        self.assertIsNone(app._app_mode(["--home", "X", "run"]))
        self.assertIsNone(app._app_mode(["doctor"]))

    def test_command_line_mode_passes_through(self):
        with mock.patch("stellenpilot.cli.main", return_value=0) as cli:
            self.assertEqual(app.main(["doctor"]), 0)
            self.assertEqual(cli.call_args.args[0], ["--home", str(app.default_home()), "doctor"])
            app.main(["--home", "W", "run"])
            self.assertEqual(cli.call_args.args[0], ["--home", "W", "run"])

    def test_frozen_app_is_started_without_python_module(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            self.assertEqual(launch.cli_command(), [sys.executable])
        self.assertEqual(launch.cli_command()[1:], ["-m", "stellenpilot.cli"])

    def test_dashboard_opens_in_its_own_window_or_falls_back_to_a_tab(self):
        url = "http://127.0.0.1:8765"
        with mock.patch.object(launch.shutil, "which", side_effect=lambda c: "/x/edge" if c == "microsoft-edge" else None), \
                mock.patch.object(launch.subprocess, "Popen") as popen, \
                mock.patch.object(launch.webbrowser, "open") as tab:
            launch.open_window(url)
            popen.assert_called_once_with(["/x/edge", f"--app={url}"])
            tab.assert_not_called()
        with mock.patch.object(launch.shutil, "which", return_value="/x/edge"), \
                mock.patch.object(launch.subprocess, "Popen", side_effect=OSError), \
                mock.patch.object(launch.webbrowser, "open") as tab:
            launch.open_window(url)  # browser found but would not start
            tab.assert_called_once_with(url)
        with mock.patch.object(launch.shutil, "which", return_value=None), \
                mock.patch.object(launch.webbrowser, "open") as tab:
            launch.open_window(url)  # no Edge or Chrome
            tab.assert_called_once_with(url)


if __name__ == "__main__":
    unittest.main()


class InitAndHomeTest(unittest.TestCase):
    def test_init_creates_a_missing_folder(self):
        import tempfile
        from stellenpilot.cli import main
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d) / "new" / "workspace"
            self.assertEqual(main(["--home", str(ws), "init"]), 0)
            self.assertTrue((ws / "config.toml").exists())

    def test_mac_keeps_files_out_of_documents(self):
        with mock.patch.object(app.sys, "platform", "darwin"):
            self.assertEqual(app.default_home(), Path.home() / "Stellenpilot")
        with mock.patch.object(app.sys, "platform", "win32"):
            self.assertEqual(app.default_home(), Path.home() / "Documents" / "Stellenpilot")
