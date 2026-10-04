"""Adapters de LLM. El resto del pipeline solo usa `get_llm(settings)`."""

from __future__ import annotations

from ..config import Settings
from .base import LLM


def get_llm(settings: Settings, dry_run: bool = False) -> LLM:
    provider = "mock" if dry_run else settings.get("llm.provider", "claude_cli")
    if provider == "mock":
        from .mock import MockLLM

        return MockLLM(settings)
    if provider == "claude_cli":
        from .claude_cli import ClaudeCLI

        return ClaudeCLI(settings)
    if provider == "anthropic_api":
        from .anthropic_api import AnthropicAPI

        return AnthropicAPI(settings)
    raise ValueError(f"llm.provider desconocido: {provider}")
