"""The Windows and Mac app (and `python -m stellenpilot.app`): start the dashboard without a terminal.

Double click: starts Stellenpilot for the default workspace (Documents/Stellenpilot; on a Mac
~/Stellenpilot), opens the
browser and shows a small window with Open and Stop. With other arguments it acts as the normal
command line, which the daily task uses: `Stellenpilot.exe --home X run`.
"""
from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path

PORT = 8765


def default_home() -> Path:
    # macOS asks for permission before an app may touch Documents, and the daily search (cron)
    # cannot answer that question. A folder in the home folder needs no permission.
    if sys.platform == "darwin":
        return Path.home() / "Stellenpilot"
    return Path.home() / "Documents" / "Stellenpilot"


def _streams(home: Path) -> None:
    # A windowed app has no console: sys.stdout is None. Send output to a log file instead.
    if sys.stdout is None or sys.stderr is None:
        home.mkdir(parents=True, exist_ok=True)
        f = open(home / "app.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115 (lives as long as the app)
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


def _app_mode(args: list[str]) -> Path | None:
    if not args:
        return default_home()
    if len(args) == 2 and args[0] == "--home":
        return Path(args[1])
    return None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    home = _app_mode(args)
    if home is None:  # command line use, e.g. the daily task
        given = args[args.index("--home") + 1] if "--home" in args[:-1] else str(default_home())
        _streams(Path(given))
        from .cli import main as cli
        if "--home" not in args:
            args = ["--home", given, *args]
        return cli(args)

    home = home.expanduser().resolve()
    home.mkdir(parents=True, exist_ok=True)
    _streams(home)
    url = f"http://127.0.0.1:{PORT}"
    from .server import _already_running, serve
    if _already_running(PORT):
        webbrowser.open(url)
        return 0
    os.chdir(home)
    from .config import Settings
    settings = Settings(home)
    failed: list[str] = []

    def run():
        try:
            serve(settings, PORT)
        except BaseException as e:  # noqa: BLE001 (shown in the window instead of a crash)
            failed.append(str(e) or e.__class__.__name__)
    threading.Thread(target=run, daemon=True).start()
    return _window(url, home, failed)


def _window(url: str, home: Path, failed: list[str]) -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:  # no Tk: keep running until the process is ended
        threading.Event().wait()
        return 0
    root = tk.Tk()
    root.title("Stellenpilot")
    root.resizable(False, False)
    try:
        from importlib import resources
        root.iconphoto(True, tk.PhotoImage(file=str(resources.files("stellenpilot") / "web" / "icon.png")).subsample(16, 16))
    except Exception:  # noqa: BLE001 (an icon is a nicety)
        pass
    frame = ttk.Frame(root, padding=20)
    frame.grid()
    title = ttk.Label(frame, text="Stellenpilot is running", font=("Segoe UI", 13, "bold"))
    title.grid(column=0, row=0, columnspan=2, sticky="w")
    body = ttk.Label(frame, text="Your dashboard is open in the browser.\nKeep this window open while you use it.\n"
                          "The daily search works even when it is closed.", justify="left")
    body.grid(column=0, row=1, columnspan=2, sticky="w", pady=(6, 14))
    ttk.Button(frame, text="Open dashboard", command=lambda: webbrowser.open(url)).grid(column=0, row=2, sticky="we", padx=(0, 8))
    ttk.Button(frame, text="Stop Stellenpilot", command=root.destroy).grid(column=1, row=2, sticky="we")
    ttk.Label(frame, text=f"Your files: {home}", foreground="#475467", wraplength=380).grid(column=0, row=3, columnspan=2, sticky="w", pady=(14, 0))
    def check():
        if failed:
            title.configure(text="Stellenpilot could not start")
            body.configure(text=failed[0])
    root.after(2000, check)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return 0  # leaving main ends the server thread; atexit stops the built-in AI


if __name__ == "__main__":
    raise SystemExit(main())
