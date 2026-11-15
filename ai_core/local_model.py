"""Local-only language model adapter and default brain factory.

The Ollama client is restricted to loopback. It never sends prompts to a hosted API.
Download the model before disconnecting; inference itself runs on the local machine.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

from ai_core.llm_brain import Brain, LLMBrain, RuleBrain


DEFAULT_LOCAL_MODEL = "qwen2.5:3b"


class OllamaClient:
    """Send chat requests only to an Ollama service on this same computer."""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None,
                 timeout_s: float = 60.0):
        self.model = model or os.environ.get("HUMANIS_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)
        self.base_url = (base_url or os.environ.get(
            "HUMANIS_OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Ollama URL must use local loopback HTTP only")
        if not self.model.strip() or timeout_s <= 0:
            raise ValueError("model must be non-empty and timeout_s must be positive")
        self.timeout_s = float(timeout_s)

    def complete(self, system: str, user: str) -> str:
        payload = json.dumps({
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0.2},
        }).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/api/chat", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ConnectionError(f"local Ollama is unavailable: {error}") from error
        message = data.get("message", {})
        answer = message.get("content") if isinstance(message, dict) else None
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Ollama returned an empty or malformed response")
        return answer


def build_default_brain(env, planner) -> Brain:
    """Prefer local Ollama; fall back to deterministic rules without network access."""
    fallback = RuleBrain(env, planner)
    mode = os.environ.get("HUMANIS_BRAIN_MODE", "local").strip().lower()
    if mode in {"rules", "offline-rules", "disabled"}:
        return fallback
    if mode not in {"local", "auto", "ollama"}:
        return fallback
    try:
        return LLMBrain(env, OllamaClient(), fallback=fallback)
    except (ValueError, RuntimeError):
        return fallback
