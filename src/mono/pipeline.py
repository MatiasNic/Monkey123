"""Orquestación de una tanda: ideas → prompts → (imágenes → QC → post-proceso → captions)."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .config import Settings
from .ideation.ideas import generate_ideas
from .llm import get_llm
from .prompting.builder import build_image_prompt
from .store import History, now_iso

log = logging.getLogger(__name__)

RECORD_KEYS = ("format", "scene", "location", "activity", "pose", "camera_distance", "expression", "gaze",
               "outfit", "lighting", "accessories", "camera_look", "concept", "concept_es", "description")


def new_batch_id(settings: Settings) -> str:
    tz = ZoneInfo(settings.get("timezone", "UTC"))
    return datetime.now(tz).strftime("%Y%m%d-%H%M") + "-" + secrets.token_hex(2)


def batch_dir(settings: Settings, batch_id: str, dry_run: bool) -> Path:
    base = settings.path("output", "dry-run") if dry_run else settings.path("drafts")
    path = base / batch_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def plan_batch(settings: Settings, count: int, fmt: str = "feed", scene: str | None = None,
               theme: str | None = None, dry_run: bool = False) -> dict:
    """Paso 1 de la tanda: ideas variadas + prompt de imagen por idea."""
    llm = get_llm(settings, dry_run=dry_run)
    ideas = generate_ideas(settings, llm, count, fmt=fmt, scene=scene, theme=theme, update_bank=not dry_run)
    batch_id = new_batch_id(settings)
    items = []
    for n, idea in enumerate(ideas, start=1):
        built = build_image_prompt(settings, idea)
        record = {"id": f"{batch_id}-{n:02d}", "batch": batch_id, "created_at": now_iso(),
                  **{k: idea.get(k) for k in RECORD_KEYS},
                  "prompt": built["prompt"], "references": built["references"],
                  "scene_photos": built["scene_photos"], "size": built["size"],
                  "provider": None, "files": {}, "qc": None, "caption": None,
                  "status": "draft", "ig_media_id": None}
        items.append(record)
    out = batch_dir(settings, batch_id, dry_run)
    batch = {"id": batch_id, "format": fmt, "scene": scene, "theme": theme, "dry_run": dry_run,
             "llm": llm.name, "items": items, "dir": str(out.relative_to(settings.root))}
    save_batch(out, batch)
    if not dry_run:
        History(settings.path("data", "history.jsonl")).append(items)
    log.info("tanda %s: %d ideas en %s", batch_id, len(items), out)
    return batch


def save_batch(folder: Path, batch: dict) -> None:
    (folder / "batch.yaml").write_text(yaml.safe_dump(batch, allow_unicode=True, sort_keys=False, width=120))


def load_batch(folder: Path) -> dict:
    return yaml.safe_load((folder / "batch.yaml").read_text())
