"""Chequeo de similitud: texto (TF-IDF coseno, local y gratis) + reglas por ejes."""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# En un carrusel es esperable repetir lugar, ropa y look entre slides.
CAROUSEL_SHARED_OK = {"location", "outfit", "camera_look", "lighting"}


def _norm(value) -> str:
    if isinstance(value, list):
        return ",".join(sorted(_norm(v) for v in value))
    return str(value or "").strip().lower()


def idea_text(idea: dict) -> str:
    parts = [idea.get("description", ""), idea.get("concept", "")]
    parts += [_norm(idea.get(k)) for k in ("location", "activity", "pose", "outfit")]
    return " ".join(p for p in parts if p)


@dataclass
class Verdict:
    ok: bool
    reason: str = ""
    similarity: float = 0.0


class Deduper:
    def __init__(self, history: list[dict], text_max: float = 0.55, max_shared_axes: int = 3,
                 key_axes: list[str] | None = None):
        self.history = history
        self.text_max = text_max
        self.max_shared_axes = max_shared_axes
        self.key_axes = key_axes or ["location", "activity", "pose", "outfit", "lighting", "camera_look"]

    @classmethod
    def from_settings(cls, settings, history: list[dict]) -> "Deduper":
        return cls(
            history,
            text_max=settings.get("dedup.text_similarity_max", 0.55),
            max_shared_axes=settings.get("dedup.max_shared_axes", 3),
            key_axes=settings.get("dedup.key_axes"),
        )

    def shared_axes(self, a: dict, b: dict, ignore: set[str] = frozenset()) -> list[str]:
        return [k for k in self.key_axes if k not in ignore and _norm(a.get(k)) and _norm(a.get(k)) == _norm(b.get(k))]

    def text_similarity(self, idea: dict, others: list[dict]) -> float:
        if not others:
            return 0.0
        corpus = [idea_text(idea)] + [idea_text(o) for o in others]
        try:
            matrix = TfidfVectorizer(stop_words="english", ngram_range=(1, 2)).fit_transform(corpus)
        except ValueError:  # vocabulario vacío
            return 0.0
        return float(cosine_similarity(matrix[0:1], matrix[1:]).max())

    def check(self, idea: dict, batch: list[dict], carousel: bool = False) -> Verdict:
        for prev in self.history:
            shared = self.shared_axes(idea, prev)
            if len(shared) > self.max_shared_axes:
                return Verdict(False, f"comparte {shared} con {prev.get('id', 'historial')}")
        ignore = CAROUSEL_SHARED_OK if carousel else set()
        for prev in batch:
            shared = self.shared_axes(idea, prev, ignore)
            same_concept = _norm(idea.get("concept")) == _norm(prev.get("concept"))
            same_activity = _norm(idea.get("activity")) == _norm(prev.get("activity"))
            if len(shared) > self.max_shared_axes or (not carousel and (same_concept or same_activity)):
                return Verdict(False, f"muy parecida a otra idea de la tanda ({shared or 'mismo concepto/actividad'})")
        # En carrusel la descripción comparte contexto entre slides: más tolerancia en la tanda.
        sim_hist = self.text_similarity(idea, self.history)
        sim_batch = self.text_similarity(idea, batch)
        limit_batch = self.text_max + (0.2 if carousel else 0.0)
        if sim_hist > self.text_max:
            return Verdict(False, f"descripción similar al historial ({sim_hist:.2f})", sim_hist)
        if sim_batch > limit_batch:
            return Verdict(False, f"descripción similar a la tanda ({sim_batch:.2f})", sim_batch)
        return Verdict(True, similarity=max(sim_hist, sim_batch))

    def select(self, candidates: list[dict], count: int, batch: list[dict] | None = None,
               carousel: bool = False) -> tuple[list[dict], list[tuple[dict, str]]]:
        accepted = list(batch or [])
        start = len(accepted)
        rejected = []
        for idea in candidates:
            if len(accepted) - start >= count:
                break
            verdict = self.check(idea, accepted, carousel=carousel)
            if verdict.ok:
                accepted.append(idea)
            else:
                rejected.append((idea, verdict.reason))
        return accepted[start:], rejected
