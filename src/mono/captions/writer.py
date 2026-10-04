"""Caption + alt text + hashtags en la voz del personaje."""

from __future__ import annotations

import json
from string import Template

from ..config import Settings
from ..llm.base import LLM
from ..store import History

SCENE_KEYS = ("concept", "description", "location", "activity", "outfit", "lighting", "camera_look")


def _scene(items: list[dict]) -> str:
    if len(items) == 1:
        return json.dumps({k: items[0].get(k) for k in SCENE_KEYS}, ensure_ascii=False, indent=1)
    slides = [{k: i.get(k) for k in ("description", "activity", "location")} for i in items]
    return "Carrusel (un caption para todo el posteo), slides en orden:\n" + json.dumps(slides, ensure_ascii=False, indent=1)


def recent_captions(settings: Settings, n: int = 12) -> list[str]:
    history = History(settings.path("data", "history.jsonl")).all()
    caps = [r["caption"]["caption"] for r in history if isinstance(r.get("caption"), dict) and r["caption"].get("caption")]
    return caps[-n:]


def clean_hashtags(tags, limit: int) -> list[str]:
    out = []
    for tag in tags or []:
        tag = "#" + str(tag).strip().lstrip("#").replace(" ", "").lower()
        if len(tag) > 1 and tag not in out:
            out.append(tag)
    return out[:limit]


def write_caption(settings: Settings, llm: LLM, items: list[dict]) -> dict:
    limit = settings.get("captions.hashtags_max", 5)
    prompt = Template(settings.prompt_template("caption")).substitute(
        language=settings.get("language", "es-AR"),
        scene=_scene(items),
        recent="\n".join(f"- {c}" for c in recent_captions(settings)) or "(ninguno todavía)",
        hashtags_max=limit,
    )
    data = llm.complete_json(prompt, task="caption", context={"items": items})
    return {
        "caption": str(data.get("caption", "")).strip(),
        "alt_text": str(data.get("alt_text", "")).strip(),
        "hashtags": clean_hashtags(data.get("hashtags"), limit),
    }


def full_text(settings: Settings, caption: dict | None) -> str:
    """Texto final que va a Instagram: caption + hashtags + disclosure opcional."""
    if not caption:
        return ""
    parts = [caption.get("caption", "")]
    if caption.get("hashtags"):
        parts.append(" ".join(caption["hashtags"]))
    if extra := settings.get("captions.ai_disclosure_text"):
        parts.append(extra)
    return "\n\n".join(p for p in parts if p)
