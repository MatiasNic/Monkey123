from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..jsonutil import extract_json


class LLM(ABC):
    """Interfaz mínima: texto (+ imágenes opcionales) → texto."""

    name = "base"

    @abstractmethod
    def complete(self, prompt: str, images: list[Path] | None = None, task: str = "", context: dict | None = None) -> str:
        """`task` y `context` solo los usa el mock para producir respuestas plausibles."""

    def complete_json(self, prompt: str, images: list[Path] | None = None, task: str = "", context: dict | None = None):
        return extract_json(self.complete(prompt, images=images, task=task, context=context))
