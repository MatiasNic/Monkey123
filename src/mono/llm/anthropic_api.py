"""Alternativa paga: API de Anthropic vía HTTP (sin SDK para no sumar dependencias)."""

from __future__ import annotations

import base64
import mimetypes

import requests

from ..config import Settings
from .base import LLM

API_URL = "https://api.anthropic.com/v1/messages"


class AnthropicAPI(LLM):
    name = "anthropic_api"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.key = settings.env("ANTHROPIC_API_KEY", required=True)
        self.model = settings.get("llm.model") or "claude-sonnet-5-5"

    def complete(self, prompt, images=None, task="", context=None) -> str:
        content = []
        for path in images or []:
            mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
            data = base64.b64encode(open(path, "rb").read()).decode()
            content.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}})
        content.append({"type": "text", "text": prompt})
        resp = requests.post(
            API_URL,
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": 8000, "messages": [{"role": "user", "content": content}]},
            timeout=self.settings.get("llm.timeout_s", 600),
        )
        resp.raise_for_status()
        return "".join(b.get("text", "") for b in resp.json()["content"] if b["type"] == "text")
