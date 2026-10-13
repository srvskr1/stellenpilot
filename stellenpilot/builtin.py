"""Built-in AI: download the llama.cpp engine and a small open model once, then run them on this computer.

Nothing to install by hand and no account or key. The files live in ~/.stellenpilot/ai (shared by all
workspaces). The engine is started when a search needs it and stopped after a few idle minutes.
"""
from __future__ import annotations

import atexit
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from .http import USER_AGENT

# Pinned so every user gets the same, tested engine. Update together with a test run.
LLAMA_BUILD = "b11602"
RELEASES = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/"
MODELS = {
    "standard": {"label": "Standard: Qwen3.5 4B", "file": "Qwen3.5-4B-Q4_K_M.gguf", "gb": 2.7,
                 "url": "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf",
                 "note": "Better writing. Needs about 6 GB of free memory."},
    "light": {"label": "Light: Qwen3.5 2B", "file": "Qwen3.5-2B-Q4_K_M.gguf", "gb": 1.3,
              "url": "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf",
              "note": "About twice as fast, simpler writing. For older computers or 8 GB of memory."},
}
CONTEXT = 8192
IDLE_STOP = 600  # seconds without a request before the engine is stopped to free memory


def ai_dir() -> Path:
    return Path(os.environ.get("STELLENPILOT_AI_DIR") or Path.home() / ".stellenpilot" / "ai").expanduser().resolve()


def engine_asset(system: str | None = None, machine: str | None = None) -> str | None:
    """File name of the CPU build for this computer, or None if llama.cpp has no ready build for it."""
    system = (system or platform.system()).lower()
    m = (machine or platform.machine()).lower()
    arm = m in ("arm64", "aarch64")
    if m not in ("x86_64", "amd64", "arm64", "aarch64"):
        return None
    if system == "windows":
        return f"llama-{LLAMA_BUILD}-bin-win-cpu-{'arm64' if arm else 'x64'}.zip"
    if system == "darwin":
        return f"llama-{LLAMA_BUILD}-bin-macos-{'arm64' if arm else 'x64'}.tar.gz"
    if system == "linux":
        return f"llama-{LLAMA_BUILD}-bin-ubuntu-{'arm64' if arm else 'x64'}.tar.gz"
    return None


def engine_path() -> Path | None:
    name = "llama-server.exe" if os.name == "nt" else "llama-server"
    found = sorted((ai_dir() / "engine").rglob(name)) if (ai_dir() / "engine").is_dir() else []
    return found[0] if found else None


def model_path(key: str) -> Path:
    return ai_dir() / "models" / MODELS.get(key, MODELS["standard"])["file"]


def status(key: str = "standard") -> dict:
    key = key if key in MODELS else "standard"
    return {"model": key, "models": {k: {**{x: v[x] for x in ("label", "gb", "note")}, "ready": model_path(k).exists()}
                                     for k, v in MODELS.items()},
            "engine": bool(engine_path()), "ready": bool(engine_path()) and model_path(key).exists(),
            "supported": engine_asset() is not None, "running": _running(), "download": dict(_dl),
            "folder": str(ai_dir())}


# ------------------------------------------------------------------ download

_dl = {"active": False, "step": "", "done": 0, "total": 0, "error": ""}


def _fetch(url: str, dest: Path, step: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:  # noqa: S310 (fixed https URLs)
        _dl.update(step=step, done=0, total=int(r.headers.get("Content-Length") or 0))
        while chunk := r.read(1 << 20):
            f.write(chunk)
            _dl["done"] += len(chunk)
    if _dl["total"] and part.stat().st_size != _dl["total"]:
        part.unlink(missing_ok=True)
        raise OSError("The download was cut off. Try again.")
    part.replace(dest)


def _safe_extract(archive: Path, target: Path) -> None:
    target = target.resolve()
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                if not (target / n).resolve().is_relative_to(target):
                    raise OSError(f"Unsafe path in the engine archive: {n}")
            z.extractall(target)
    else:
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                if not (target / m.name).resolve().is_relative_to(target) or m.isdev():
                    raise OSError(f"Unsafe path in the engine archive: {m.name}")
                if (m.issym() or m.islnk()) and not (target / m.name).parent.joinpath(m.linkname).resolve().is_relative_to(target):
                    raise OSError(f"Unsafe link in the engine archive: {m.name}")
            if hasattr(tarfile, "data_filter"):
                t.extractall(target, filter="data")
            else:
                t.extractall(target)  # noqa: S202 (members checked above)


def install_engine() -> Path:
    if engine_path():
        return engine_path()
    asset = engine_asset()
    if not asset:
        raise RuntimeError(f"There is no ready made AI engine for {platform.system()} on {platform.machine()}. "
                           "Use Ollama or an API key instead.")
    archive = ai_dir() / asset
    _fetch(RELEASES + asset, archive, "engine")
    _dl["step"] = "unpack"
    target = ai_dir() / "engine"
    shutil.rmtree(target, ignore_errors=True)
    _safe_extract(archive, target)
    archive.unlink(missing_ok=True)
    exe = engine_path()
    if not exe:
        raise RuntimeError("The engine download did not contain llama-server. Please report this as a bug.")
    if os.name != "nt":
        for f in exe.parent.iterdir():
            if f.is_file():
                f.chmod(f.stat().st_mode | 0o755)
    return exe


def download(key: str = "standard") -> None:
    """Engine plus model. Blocking; the dashboard runs it in a thread and reads _dl for progress."""
    key = key if key in MODELS else "standard"
    _dl.update(active=True, error="", step="", done=0, total=0)
    try:
        install_engine()
        if not model_path(key).exists():
            _fetch(MODELS[key]["url"], model_path(key), "model")
        _dl["step"] = "done"
    except Exception as e:
        _dl["error"] = _plain(e)
        raise
    finally:
        _dl["active"] = False


def start_download(key: str) -> bool:
    if _dl["active"]:
        return False
    threading.Thread(target=lambda: _quiet(download, key), daemon=True).start()
    return True


def remove() -> None:
    stop()
    shutil.rmtree(ai_dir(), ignore_errors=True)


def _quiet(fn, *a):
    try:
        fn(*a)
    except Exception:  # noqa: BLE001 (the error is kept in _dl for the dashboard)
        pass


def _plain(e: Exception) -> str:
    text = str(e)
    if isinstance(e, OSError) and ("getaddrinfo" in text or "timed out" in text or "Connection" in text):
        return "Could not download. Check the internet connection and try again."
    if "No space left" in text:
        return "Not enough free disk space. The AI needs about 3 GB."
    return text


# ------------------------------------------------------------------ engine process

_proc: subprocess.Popen | None = None
_port = 0
_key = ""
_last = 0.0
_lock = threading.Lock()


def _running() -> bool:
    return _proc is not None and _proc.poll() is None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:  # noqa: S310
            return r.status == 200
    except OSError:
        return False


def ensure_running(key: str = "standard") -> str:
    """Start the engine if needed and return its OpenAI compatible base URL."""
    global _proc, _port, _key, _last
    key = key if key in MODELS else "standard"
    with _lock:
        _last = time.time()
        if _running() and _key == key:
            return f"http://127.0.0.1:{_port}/v1"
        stop(locked=True)
        exe, model = engine_path(), model_path(key)
        if not exe or not model.exists():
            raise RuntimeError("The built-in AI is not downloaded yet. Open Settings, AI model, and press Download.")
        port = _free_port()
        log = open(ai_dir() / "engine.log", "ab")  # noqa: SIM115 (kept open for the process)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        _proc = subprocess.Popen([str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
                                  "-c", str(CONTEXT), "--reasoning-budget", "0"],
                                 stdout=log, stderr=log, stdin=subprocess.DEVNULL, cwd=str(exe.parent),
                                 creationflags=flags)
        _port, _key = port, key
        deadline = time.time() + 180  # loading a model from a slow disk can take a while
        while time.time() < deadline:
            if _proc.poll() is not None:
                raise RuntimeError(f"The built-in AI stopped while starting. Details are in {ai_dir() / 'engine.log'}")
            if _healthy(port):
                _watch()
                return f"http://127.0.0.1:{port}/v1"
            time.sleep(0.5)
        stop(locked=True)
        raise RuntimeError("The built-in AI took too long to start. Close other programs and try again.")


def speed_test(key: str = "standard") -> dict:
    """Start the engine and time a realistic request. Returns speeds and minutes per job and per document."""
    from .http import request_json
    t0 = time.time()
    base = ensure_running(key)
    started = time.time() - t0
    ad = ("We are looking for a working student in data engineering. You build Python and SQL pipelines, "
          "work with cloud tools and help the analytics team with reports. ") * 14
    body = {"model": key, "max_tokens": 160, "temperature": 0.2, "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "system", "content": "You help a job seeker. Answer in plain English."},
                         {"role": "user", "content": ad + "\n\nIn about 100 words, say who would fit this job."}]}
    data = request_json(f"{base}/chat/completions", method="POST", timeout=600, body=body, retries=0)
    touch()
    t = data.get("timings") or {}
    pp, tg = float(t.get("prompt_per_second") or 0), float(t.get("predicted_per_second") or 0)
    if not (pp and tg):
        raise RuntimeError("The engine answered without timing data.")
    # Fitted to real runs with both models (October 2026, 2 core test server): scoring one job and
    # tailoring one CV plus cover letter, timed end to end. Within about 15 percent there.
    job = 1300 / pp + 140 / tg
    doc = 2500 / pp + 270 / tg
    return {"start_seconds": round(started), "read_per_second": round(pp), "write_per_second": round(tg, 1),
            "seconds_per_job": round(job), "minutes_per_document": round(doc / 60, 1),
            "minutes_daily": round((20 * job + 5 * doc) / 60)}  # 20 jobs read by the AI, up to 5 CVs a run


def touch() -> None:
    global _last
    _last = time.time()


def stop(locked: bool = False) -> None:
    global _proc
    if not locked:
        with _lock:
            return stop(locked=True)
    if _proc is not None:
        if _proc.poll() is None:
            _proc.terminate()
            try:
                _proc.wait(10)
            except subprocess.TimeoutExpired:
                _proc.kill()
        _proc = None


_watching = False


def _watch() -> None:
    global _watching
    if _watching:
        return
    _watching = True

    def loop():
        global _watching
        while _running():
            time.sleep(30)
            if time.time() - _last > IDLE_STOP:
                stop()
        _watching = False
    threading.Thread(target=loop, daemon=True).start()


atexit.register(stop)


def main(argv=None) -> int:
    """python -m stellenpilot.builtin [standard|light]: download from the terminal."""
    key = (argv or sys.argv[1:] or ["standard"])[0]
    t = threading.Thread(target=lambda: _quiet(download, key))
    t.start()
    while t.is_alive():
        time.sleep(1)
        if _dl["total"]:
            print(f"\r{_dl['step']}: {_dl['done'] / 1e6:.0f} of {_dl['total'] / 1e6:.0f} MB", end="", flush=True)
    print()
    if _dl["error"]:
        print("Problem:", _dl["error"])
        return 1
    print("Built-in AI ready in", ai_dir())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
