"""LLM falso y determinista para --dry-run y tests: no hace llamadas de red."""

from __future__ import annotations

import json
import random

from ..config import Settings
from .base import LLM


class MockLLM(LLM):
    name = "mock"

    def __init__(self, settings: Settings, seed: int = 7):
        self.settings = settings
        self.rng = random.Random(seed)

    def complete(self, prompt, images=None, task="", context=None) -> str:
        context = context or {}
        handler = getattr(self, f"_{task}", None)
        if handler is None:
            return json.dumps({"ok": True})
        return json.dumps(handler(context), ensure_ascii=False)

    def _ideation(self, ctx: dict) -> dict:
        axes = self.settings.bible["axes"]
        looks = list(self.settings.bible["camera_looks"])
        bank = ctx.get("bank", [])
        ideas = []
        for _ in range(ctx.get("count", 4) * 2):
            pick = {k: self.rng.choice(v) for k, v in axes.items()}
            concept = self.rng.choice(bank) if bank and self.rng.random() < 0.5 else pick["activity"]
            ideas.append({
                "concept": concept,
                "format": ctx.get("format", "feed"),
                "scene": ctx.get("scene") or None,
                **pick,
                "accessories": [pick["accessories"]],
                "camera_look": self.rng.choice(looks),
                "description": (
                    f"The macaque {pick['activity']} at a {pick['location']}, {pick['pose']}, "
                    f"wearing {pick['outfit']}, {pick['expression']} expression, gaze {pick['gaze']}, "
                    f"{pick['lighting']}, {pick['camera_distance']} shot."
                ),
                "concept_es": f"[mock] {concept}",
            })
        return {"ideas": ideas, "new_bank_ideas": [f"mock idea {self.rng.randint(0, 999)}"]}

    def _qc(self, ctx: dict) -> dict:
        return {"score": 8.2, "identity_match": 8, "species_ok": True, "anatomy": 8, "limb_count_ok": True, "anatomy_issues": [], "scale_ok": True, "is_collage": False, "has_text": False,
                "ai_look": 3, "matches_idea": 8, "reasons": ["mock QC: sin evaluación real"]}

    def _caption(self, ctx: dict) -> dict:
        return {"caption": "otro martes.", "alt_text": "Un macaco con ropa urbana en una escena cotidiana.",
                "hashtags": ["#buenosaires", "#vidaurbana", "#35mm"]}
