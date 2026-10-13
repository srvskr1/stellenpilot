import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from stellenpilot import shortcut


class ShortcutTest(unittest.TestCase):
    @unittest.skipIf(sys.platform.startswith("win") or sys.platform == "darwin", "Linux layout")
    def test_linux_menu_entry_and_desktop_copy(self):
        with tempfile.TemporaryDirectory() as d:
            home, ws = Path(d), Path(d) / "my hunt"
            (home / "Desktop").mkdir()
            ws.mkdir()
            shortcut.desktop_dir.cache_clear()
            with mock.patch.dict(os.environ, {"HOME": str(home), "XDG_DATA_HOME": str(home / "share")}):
                where = shortcut.create(ws)
                self.assertEqual(where, home / "Desktop" / "stellenpilot.desktop")
                text = where.read_text()
                self.assertIn(f'Exec="{sys.executable}" -m stellenpilot serve --home "{ws}"' if " " in sys.executable
                              else f'Exec={sys.executable} -m stellenpilot serve --home "{ws}"', text)
                self.assertIn("icon.png", text)
                self.assertTrue(shortcut.exists())
            shortcut.desktop_dir.cache_clear()

    @unittest.skipUnless(sys.platform.startswith("win"), "needs Windows")
    def test_windows_shortcut_points_at_this_python(self):
        with tempfile.TemporaryDirectory() as d:
            where = shortcut.create(Path(d) / "ws with space")
            try:
                out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                      f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{where}');$s.TargetPath;$s.Arguments"],
                                     capture_output=True, text=True, check=True).stdout
                self.assertIn(Path(sys.executable).name, out)
                self.assertIn("-m stellenpilot serve --home", out)
                self.assertIn("ws with space", out)
            finally:
                where.unlink(missing_ok=True)


class AlreadyRunningTest(unittest.TestCase):
    def test_second_start_does_not_crash(self):
        from stellenpilot import server
        with mock.patch.object(server, "ThreadingHTTPServer", side_effect=OSError("in use")), \
             mock.patch.object(server, "_already_running", return_value=True), \
             mock.patch("webbrowser.open") as opened, \
             mock.patch.object(server, "make_handler"):
            server.serve({"schedule": {}}, 8765, open_browser=True)
            opened.assert_called_once()
        with mock.patch.object(server, "ThreadingHTTPServer", side_effect=OSError("in use")), \
             mock.patch.object(server, "_already_running", return_value=False), \
             mock.patch.object(server, "make_handler"):
            with self.assertRaises(SystemExit):
                server.serve({"schedule": {}}, 8765, open_browser=False)


if __name__ == "__main__":
    unittest.main()
