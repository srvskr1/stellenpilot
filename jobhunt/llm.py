"""LLM access: Anthropic, any OpenAI compatible server (OpenAI, Ollama, LM Studio), or none."""
from __future__ import annotations

import json
import re

from .http import request_json


class LLM:
    def __init__(self, settings):
        c = settings["llm"]
        self.provider = (c.get("provider") or "none").lower()
        self.model = c.get("model")
        self.base_url = (c.get("base_url") or "").rstrip("/")
        self.settings = settings
        if self.provider == "anthropic" and not settings.secret("ANTHROPIC_API_KEY"):
            raise RuntimeError("llm.provider is anthropic but ANTHROPIC_API_KEY is not set")

    @property
    def enabled(self) -> bool:
        return self.provider in ("anthropic", "openai")

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        if self.provider == "anthropic":
            data = request_json(
                "https://api.anthropic.com/v1/messages", method="POST", timeout=120,
                headers={"x-api-key": self.settings.secret("ANTHROPIC_API_KEY"),
                         "anthropic-version": "2023-06-01"},
                body={"model": self.model, "max_tokens": max_tokens, "system": system,
                      "messages": [{"role": "user", "content": user}]})
            return "".join(b.get("text", "") for b in data.get("content", []))
        if self.provider == "openai":
            base = self.base_url or "https://api.openai.com/v1"
            key = self.settings.secret("OPENAI_API_KEY")
            data = request_json(
                f"{base}/chat/completions", method="POST", timeout=180,
                headers={"Authorization": f"Bearer {key}"} if key else {},
                body={"model": self.model, "max_tokens": max_tokens,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}]})
            return data["choices"][0]["message"]["content"]
        raise RuntimeError("No LLM configured (llm.provider = none)")

    def complete_json(self, system: str, user: str, max_tokens: int = 1500) -> dict:
        text = self.complete(system + "\nReply with one JSON object and nothing else.", user, max_tokens)
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError(f"LLM did not return JSON: {text[:200]}")
        return json.loads(m.group(0))
