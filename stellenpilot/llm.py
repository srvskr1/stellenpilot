"""LLM access: Anthropic, OpenAI, or a local model (Ollama, LM Studio, llama.cpp, vLLM, any
OpenAI compatible server), or none.

Local models are first class: nothing leaves your machine, there is no API cost, and the
truth guard in tailor.py still checks everything they write.
"""
from __future__ import annotations

import json
import os
import re

from .http import HttpError, request_json

# provider -> default base URL. All except ollama speak the OpenAI chat completions API.
LOCAL_PRESETS = {
    "ollama": "http://localhost:11434",       # native Ollama API, lets us set the context size
    "lmstudio": "http://localhost:1234/v1",
    "llamacpp": "http://localhost:8080/v1",   # llama.cpp server or llama-cpp-python server
    "vllm": "http://localhost:8000/v1",
    "local": "",                              # any OpenAI compatible server: set base_url
    "builtin": "",                            # Stellenpilot's own llama.cpp engine, started on demand
}
CLOUD = {"anthropic", "openai"}


class LLM:
    def __init__(self, settings):
        c = settings["llm"]
        self.provider = (c.get("provider") or "none").lower()
        if self.provider not in CLOUD | set(LOCAL_PRESETS) | {"none"}:
            raise RuntimeError(f"Unknown llm.provider '{self.provider}'. Use one of: none, anthropic, openai, {', '.join(LOCAL_PRESETS)}")
        self.model = c.get("model") or {"anthropic": "claude-haiku-4-5-20251001", "builtin": "standard"}.get(self.provider, "")
        self.local = self.provider in LOCAL_PRESETS
        # JOBHUNT_LLM_BASE_URL overrides the config, handy in Docker (host.docker.internal).
        base = os.environ.get("JOBHUNT_LLM_BASE_URL") or c.get("base_url") or LOCAL_PRESETS.get(self.provider, "")
        self.base_url = base.rstrip("/")
        self.timeout = float(c.get("timeout") or (600 if self.local else 120))
        self.json_mode = c.get("json_mode", True)
        self.num_ctx = int(c.get("num_ctx") or 8192)
        self.think = bool(c["think"]) if "think" in c else False
        self.temperature = float(c.get("temperature", 0.2))
        # Small local models have small context windows; long ads get cut to this many characters.
        self.max_chars = int(c.get("max_input_chars") or (4000 if self.local else 6000))
        self.settings = settings
        if self.provider == "anthropic" and not settings.secret("ANTHROPIC_API_KEY"):
            raise RuntimeError("llm.provider is anthropic but ANTHROPIC_API_KEY is not set")
        if self.provider == "openai" and not settings.secret("OPENAI_API_KEY") and not self.base_url:
            raise RuntimeError("llm.provider is openai but OPENAI_API_KEY is not set")
        if self.provider == "builtin":
            from . import builtin
            self.model = self.model if self.model in builtin.MODELS else "standard"
            self.base_url = ""  # set when the engine starts
        if self.provider == "local" and not self.base_url:
            raise RuntimeError("llm.provider is local: set llm.base_url, e.g. http://localhost:8080/v1")
        if self.enabled and not self.model:
            raise RuntimeError("Set llm.model in config.toml (for Ollama e.g. qwen3.5:4b)")

    @property
    def enabled(self) -> bool:
        return self.provider != "none"

    # ------------------------------------------------------------ calls

    def complete(self, system: str, user: str, max_tokens: int = 1500, want_json: bool = False) -> str:
        if self.provider == "anthropic":
            data = request_json(
                "https://api.anthropic.com/v1/messages", method="POST", timeout=self.timeout,
                headers={"x-api-key": self.settings.secret("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"},
                body={"model": self.model, "max_tokens": max_tokens, "system": system,
                      "messages": [{"role": "user", "content": user}]})
            return "".join(b.get("text", "") for b in data.get("content", []))
        if self.provider == "ollama":
            body = {"model": self.model, "stream": False,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "options": {"num_ctx": self.num_ctx, "temperature": self.temperature, "num_predict": max_tokens}}
            if want_json and self.json_mode:
                body["format"] = "json"
            if self.think is not None:
                # Qwen3/3.5 and Gemma 4 think before answering by default; for short JSON tasks that
                # only costs time and output tokens. llm.think = true turns it back on.
                body["think"] = self.think
            try:
                data = request_json(f"{self.base_url}/api/chat", method="POST", timeout=self.timeout, body=body, retries=0)
            except HttpError as e:
                if "think" in body and e.status == 400 and "think" in str(e).lower():
                    self.think = None  # this model or an older Ollama does not know the option
                    body.pop("think")
                    data = request_json(f"{self.base_url}/api/chat", method="POST", timeout=self.timeout, body=body, retries=0)
                else:
                    raise
            return strip_thinking((data.get("message") or {}).get("content", ""))
        if self.provider == "none":
            raise RuntimeError("No LLM configured (llm.provider = none)")
        return self._openai_compatible(system, user, max_tokens, want_json)

    def _openai_compatible(self, system: str, user: str, max_tokens: int, want_json: bool) -> str:
        if self.provider == "builtin":
            from . import builtin
            self.base_url = builtin.ensure_running(self.model)
        base = self.base_url or "https://api.openai.com/v1"
        key = self.settings.secret("OPENAI_API_KEY")
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": self.temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if want_json and self.json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.provider == "builtin":
            body["chat_template_kwargs"] = {"enable_thinking": self.think}  # Qwen3.5 thinks by default; slow on a CPU
        headers = {"Authorization": f"Bearer {key}"} if key and not self.local else {}
        try:
            data = request_json(f"{base}/chat/completions", method="POST", timeout=self.timeout,
                                headers=headers, body=body, retries=0 if self.local else 2)
        except HttpError as e:
            # Some servers (older LM Studio, some llama.cpp builds) reject json_object. Retry plain, remember it.
            if "response_format" in body and e.status in (400, 422, 500):
                self.json_mode = False
                body.pop("response_format")
                data = request_json(f"{base}/chat/completions", method="POST", timeout=self.timeout,
                                    headers=headers, body=body, retries=0)
            else:
                raise
        if self.provider == "builtin":
            from . import builtin
            builtin.touch()
        return strip_thinking(data["choices"][0]["message"]["content"] or "")

    def complete_json(self, system: str, user: str, max_tokens: int = 1500) -> dict:
        system = system + "\nReply with one JSON object and nothing else."
        text = self.complete(system, user, max_tokens, want_json=True)
        try:
            return parse_json(text)
        except ValueError:
            # Small models sometimes wrap or break the JSON. One retry with a firm reminder.
            text = self.complete(system, user + "\n\nYour last reply was not valid JSON. Reply with ONLY the JSON object.",
                                 max_tokens, want_json=True)
            return parse_json(text)

    # ------------------------------------------------------------ setup checks

    @property
    def ai_job_limit(self) -> int:
        """How many new jobs per run the AI scores. A model on your own CPU is slow, so it reads the most
        promising ones (by keyword score) and the rest keep their keyword score. 0 means no limit."""
        c = self.settings["llm"]
        if "max_ai_jobs" in c:
            return max(0, int(c["max_ai_jobs"]))
        return 20 if self.local else 0

    def list_models(self) -> list[str]:
        """Models the local server offers. Raises if the server cannot be reached."""
        if self.provider == "ollama":
            data = request_json(f"{self.base_url}/api/tags", timeout=10, retries=0)
            return [m.get("name", "") for m in data.get("models", [])]
        data = request_json(f"{self.base_url}/models", timeout=10, retries=0)
        return [m.get("id", "") for m in data.get("data", [])]


def strip_thinking(text: str) -> str:
    """Drop <think>...</think> blocks that reasoning models put before the answer."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    return text.split("</think>", 1)[-1].strip() if "</think>" in text else text.strip()


def parse_json(text: str) -> dict:
    """First JSON object in the text, tolerating code fences and chatter around it."""
    text = re.sub(r"```(?:json)?", "", text or "")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"LLM did not return JSON: {text[:200]}")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError(f"LLM returned incomplete JSON: {text[:200]}")
