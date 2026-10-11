"""Daily automatic search: creates or removes the operating system's own scheduled task.

Windows: a Task Scheduler task that also runs after a missed start (PC was off at that time).
macOS and Linux: one crontab line, marked so it can be found and removed again.
The command runs `stellenpilot run` with the same Python as the dashboard, logging to run.log.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

TASK_NAME = "Stellenpilot daily search"
OLD_TASK_NAMES = ("JobHunt daily search", "JobRadar daily search")
MARK = "# jobhunt-daily"


class ScheduleError(RuntimeError):
    pass


def parse_time(value: str) -> tuple[int, int]:
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", (value or "").strip())
    if not m:
        raise ScheduleError("Use a time like 08:45.")
    return int(m.group(1)), int(m.group(2))


def in_docker() -> bool:
    return Path("/.dockerenv").exists()


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30, **kw)
    except FileNotFoundError:
        raise ScheduleError(f"{cmd[0]} was not found on this computer, so the automatic search cannot be set up here. "
                            "See docs/scheduling.md for doing it by hand.") from None


def _windows_xml(script: Path, hour: int, minute: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Daily job search by stellenpilot</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T{hour:02d}:{minute:02d}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Settings>
    <StartWhenAvailable>true</StartWhenAvailable>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <ExecutionTimeLimit>PT3H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec><Command>{escape(str(script))}</Command></Exec></Actions>
</Task>
"""


def enable(home: Path, time: str) -> str:
    """Create or update the daily task. Returns a sentence for the user."""
    hour, minute = parse_time(time)
    if in_docker():
        raise ScheduleError("Inside Docker the dashboard cannot set up a task on your computer. "
                            "See docs/docker.md for a daily run with cron or Task Scheduler.")
    home = home.resolve()
    log = home / "run.log"
    if sys.platform.startswith("win"):
        script = home / "jobhunt-daily.cmd"
        script.write_text(f'@echo off\r\ncd /d "{home}"\r\n"{sys.executable}" -m stellenpilot.cli --home "{home}" run >> "{log}" 2>&1\r\n',
                          encoding="utf-8")
        for old in OLD_TASK_NAMES:
            _run(["schtasks", "/Delete", "/TN", old, "/F"])
        xml = home / "jobhunt-daily.xml"
        xml.write_text(_windows_xml(script, hour, minute), encoding="utf-16")
        r = _run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml), "/F"])
        xml.unlink(missing_ok=True)
        if r.returncode != 0:
            raise ScheduleError(f"Windows refused to create the task: {(r.stderr or r.stdout).strip()}")
        return f"Every day at {hour:02d}:{minute:02d}. If the PC is off then, it runs as soon as you log in."
    line = (f"{minute} {hour} * * * cd {shlex.quote(str(home))} && {shlex.quote(sys.executable)} -m stellenpilot.cli "
            f"--home {shlex.quote(str(home))} run >> {shlex.quote(str(log))} 2>&1 {MARK} {home}")
    _write_crontab([ln for ln in _read_crontab() if not _ours(ln, home)] + [line])
    return f"Every day at {hour:02d}:{minute:02d} while the computer is awake. Missed runs happen when you open the dashboard."


def disable(home: Path) -> None:
    home = home.resolve()
    if in_docker():
        return
    if sys.platform.startswith("win"):
        for old in OLD_TASK_NAMES:
            _run(["schtasks", "/Delete", "/TN", old, "/F"])
        r = _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
        if r.returncode != 0 and is_enabled(home):
            raise ScheduleError(f"Windows refused to remove the task: {(r.stderr or r.stdout).strip()}")
        (home / "jobhunt-daily.cmd").unlink(missing_ok=True)
        return
    lines = _read_crontab()
    if any(_ours(ln, home) for ln in lines):
        _write_crontab([ln for ln in lines if not _ours(ln, home)])


def is_enabled(home: Path) -> bool:
    """Whether the operating system really has the task (it may have been removed by hand)."""
    if in_docker():
        return False
    try:
        if sys.platform.startswith("win"):
            return _run(["schtasks", "/Query", "/TN", TASK_NAME]).returncode == 0
        return any(_ours(ln, home.resolve()) for ln in _read_crontab())
    except ScheduleError:
        return False


def _ours(line: str, home: Path) -> bool:
    return line.rstrip().endswith(f"{MARK} {home}")


def _read_crontab() -> list[str]:
    r = _run(["crontab", "-l"])
    return r.stdout.splitlines() if r.returncode == 0 else []  # no crontab yet is fine


def _write_crontab(lines: list[str]) -> None:
    r = _run(["crontab", "-"], input="\n".join(lines) + "\n")
    if r.returncode != 0:
        raise ScheduleError(f"Could not update your crontab: {r.stderr.strip()}")


def missed_today(settings, last_run_date: str | None, now=None) -> bool:
    """True when the scheduled time has passed by 30 minutes today and no run happened today."""
    from datetime import datetime, timedelta
    cfg = settings["schedule"]
    if not cfg.get("enabled"):
        return False
    now = now or datetime.now()
    try:
        hour, minute = parse_time(cfg.get("time", ""))
    except ScheduleError:
        return False
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(minutes=30)
    return now >= due and last_run_date != now.date().isoformat()


if __name__ == "__main__":  # quick self check of the pure parts
    assert parse_time("8:05") == (8, 5) and parse_time("23:59") == (23, 59)
    for bad in ("24:00", "8.30", "", "08:60"):
        try:
            parse_time(bad)
            raise AssertionError(bad)
        except ScheduleError:
            pass
    print("ok", os.name)
