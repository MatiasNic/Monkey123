"""Generación de ideas con Claude + filtro de variedad contra historial y tanda."""

from __future__ import annotations

import json
import logging
from string import Template

import yaml

from ..config import Settings
from ..llm.base import LLM
from ..store import History, IdeaBank
from .dedup import Deduper

log = logging.getLogger(__name__)

SUMMARY_KEYS = ("location", "activity", "pose", "camera_distance", "outfit", "lighting", "camera_look")


def summarize(record: dict) -> str:
    return " | ".join(f"{k}={record.get(k)}" for k in SUMMARY_KEYS if record.get(k))


def build_ideation_prompt(settings: Settings, recent: list[dict], bank: list[str], count: int,
                          fmt: str, scene: str | None, theme: str | None) -> str:
    bible = settings.bible
    scene_text = "ninguna"
    if scene:
        scene_file = settings.path("scenes", scene, "scene.yaml")
        scene_text = scene_file.read_text() if scene_file.exists() else scene
    return Template(settings.prompt_template("ideation")).safe_substitute(
        identity=yaml.safe_dump(bible["identity"], allow_unicode=True, sort_keys=False),
        axes=yaml.safe_dump(bible["axes"], allow_unicode=True, sort_keys=False, width=200),
        looks=", ".join(bible["camera_looks"]),
        recent="\n".join(f"- {summarize(r)}" for r in recent) or "(sin historial todavía)",
        bank="\n".join(f"- {c}" for c in bank[:30]) or "(vacío)",
        count=count,
        overgen=count * 2,
        format=fmt,
        scene=scene_text,
        theme=theme or "libre",
    )


def normalize(idea: dict, settings: Settings, fmt: str, scene: str | None) -> dict:
    looks = settings.bible["camera_looks"]
    idea = dict(idea)
    idea["format"] = fmt
    idea["scene"] = scene or idea.get("scene") or None
    if idea.get("camera_look") not in looks:
        idea["camera_look"] = next(iter(looks))
    if isinstance(idea.get("accessories"), str):
        idea["accessories"] = [idea["accessories"]]
    idea.setdefault("accessories", [])
    return idea


def generate_ideas(settings: Settings, llm: LLM, count: int, fmt: str = "feed", scene: str | None = None,
                   theme: str | None = None, max_rounds: int = 3, update_bank: bool = True) -> list[dict]:
    history = History(settings.path("data", "history.jsonl"))
    bank = IdeaBank(settings.path("data", "idea_bank.yaml"))
    recent = history.recent(settings.get("dedup.compare_last", 40))
    deduper = Deduper.from_settings(settings, recent)
    carousel = fmt in ("carousel", "reel")  # secuencia: misma salida, momentos distintos

    accepted: list[dict] = []
    for round_no in range(1, max_rounds + 1):
        missing = count - len(accepted)
        if missing <= 0:
            break
        prompt = build_ideation_prompt(settings, recent + accepted, bank.unused(), missing, fmt, scene, theme)
        result = llm.complete_json(prompt, task="ideation",
                                   context={"count": missing, "format": fmt, "scene": scene, "bank": bank.unused()})
        candidates = [normalize(i, settings, fmt, scene) for i in result.get("ideas", [])]
        new, rejected = deduper.select(candidates, missing, batch=accepted, carousel=carousel)
        accepted += new
        for idea, reason in rejected:
            log.info("descartada (ronda %d): %s → %s", round_no, idea.get("concept"), reason)
        if update_bank and result.get("new_bank_ideas"):
            bank.extend(result["new_bank_ideas"])
    if update_bank:
        bank.mark_used([i.get("concept", "") for i in accepted])
    if len(accepted) < count:
        log.warning("solo %d/%d ideas superaron el filtro de variedad", len(accepted), count)
    return accepted


def dumps(ideas: list[dict]) -> str:
    return json.dumps(ideas, ensure_ascii=False, indent=2)
