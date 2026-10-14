"""Live progress of slow AI work (reading a CV, writing documents) for the dashboard.

An AI on your own processor can take ten minutes to read a CV. Without feedback that looks
broken, so the work reports what it is doing: starting the AI, reading, writing (with the
number of characters written so far and an estimate of the total), checking and saving.
The dashboard polls GET /api/progress?task=... while it waits.

One person uses one dashboard, so a small in-memory table keyed by task name is enough.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager

_lock = threading.Lock()
_tasks: dict[str, dict] = {}
_current = threading.local()  # the task this thread reports to, so deep code needs no extra arguments

# Section names the AI writes, and how the dashboard calls them.
SECTIONS = (('"skills"', "skills"), ('"experience"', "jobs"), ('"projects"', "projects"), ('"education"', "degrees"))


def _now() -> float:
    return time.monotonic()


class Busy(RuntimeError):
    """The same kind of work is already running."""


@contextmanager
def track(task: str, label: str = "", exclusive: bool = True):
    """Report progress for `task` from this thread while the block runs. With `exclusive`, a second
    start while the first still runs raises Busy, so two runs cannot overwrite each other's results."""
    with _lock:
        if exclusive and (_tasks.get(task) or {}).get("active"):
            raise Busy("This is already running. Wait until it is finished.")
        _tasks[task] = {"active": True, "label": label, "stage": "Starting", "chars": 0, "expect": 0,
                        "found": [], "started": _now(), "stage_started": _now(), "error": "", "step": 0, "steps": 0}
    prev = getattr(_current, "task", None)
    _current.task = task
    try:
        yield
    except Exception as e:
        with _lock:
            _tasks[task]["error"] = str(e)[:300]
        raise
    finally:
        _current.task = prev
        with _lock:
            _tasks[task]["active"] = False
            _tasks[task]["ended"] = _now()


def current() -> str | None:
    return getattr(_current, "task", None)


def stage(text: str, expect: int = 0, step: int = 0, steps: int = 0) -> None:
    """A new step of the work. `expect` is about how many characters the AI will write in it."""
    task = current()
    if not task:
        return
    with _lock:
        t = _tasks.get(task)
        if t:
            t.update(stage=text, chars=0, expect=int(expect), stage_started=_now())
            if steps:
                t.update(step=step, steps=steps)


@contextmanager
def aside(text: str):
    """Show `text` for a moment (like starting the AI), then return to the step that was running."""
    task = current()
    with _lock:
        t = _tasks.get(task) if task else None
        saved = (t["stage"], t["stage_started"]) if t else None
        if t:
            t["stage"] = text
    try:
        yield
    finally:
        with _lock:
            if t and saved:
                t["stage"], t["stage_started"] = saved[0], _now()


def writing(text_so_far: str) -> None:
    """Called while the AI streams its answer."""
    task = current()
    if not task:
        return
    with _lock:
        t = _tasks.get(task)
        if not t:
            return
        t["chars"] = len(text_so_far)
        for key, name in SECTIONS:
            if name not in t["found"] and key in text_so_far:
                t["found"].append(name)


def snapshot(task: str) -> dict:
    with _lock:
        t = dict(_tasks.get(task) or {})
    if not t:
        return {"active": False}
    end = t.get("ended") or _now()
    elapsed = end - t["started"]
    out = {k: t[k] for k in ("active", "label", "stage", "chars", "expect", "found", "error", "step", "steps")}
    out["elapsed"] = round(elapsed)
    out["percent"] = None
    if t["expect"] and t["chars"]:
        out["percent"] = min(97, round(100 * t["chars"] / t["expect"]))
        spent = end - t["stage_started"]
        rate = t["chars"] / spent if spent > 0 else 0
        left = max(0, t["expect"] - t["chars"])
        out["eta"] = round(left / rate) if rate > 0 else None
    return out


def busy(task: str) -> bool:
    with _lock:
        return bool((_tasks.get(task) or {}).get("active"))
