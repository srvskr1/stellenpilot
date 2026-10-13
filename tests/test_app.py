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


if __name__ == "__main__":
    unittest.main()
