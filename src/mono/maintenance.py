"""Estado del token de Instagram y limpieza de medios viejos del repo."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .config import Settings

log = logging.getLogger(__name__)
TERMINAL = {"published", "discarded", "failed"}
MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".mp4"}


def _status_path(settings: Settings) -> Path:
    return settings.path("data", "token_status.yaml")


def record_token_refresh(settings: Settings, expires_in: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    data = {"refreshed_at": now.isoformat(timespec="seconds"),
            "expires_at": (now + timedelta(seconds=int(expires_in))).isoformat(timespec="seconds")}
    _status_path(settings).write_text("# Vencimiento del token de Instagram (no es secreto).\n" +
                                      yaml.safe_dump(data, sort_keys=False))
    return data


def token_days_left(settings: Settings, now: datetime | None = None) -> float | None:
    path = _status_path(settings)
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text()) or {}
    if not data.get("expires_at"):
        return None
    now = now or datetime.now(timezone.utc)
    return (datetime.fromisoformat(data["expires_at"]) - now).total_seconds() / 86400


def prune_media(settings: Settings, days: int = 60, now: datetime | None = None, dry_run: bool = False) -> list[Path]:
    """Borra JPG/MP4 de tandas cuyas piezas están todas publicadas/descartadas hace más de `days` días.

    Se conservan batch.yaml, batch.md y el historial (con el permalink de Instagram).
    """
    now = now or datetime.now(timezone.utc)
    removed = []
    for batch_file in sorted(settings.path("drafts").glob("*/batch.yaml")):
        batch = yaml.safe_load(batch_file.read_text())
        items = batch.get("items") or []
        if not items or any(i.get("status") not in TERMINAL for i in items):
            continue
        newest = max(datetime.fromisoformat(i["created_at"]) for i in items)
        if now - newest < timedelta(days=days):
            continue
        for media in sorted(p for p in batch_file.parent.rglob("*") if p.suffix.lower() in MEDIA_EXTS):
            removed.append(media)
            if not dry_run:
                media.unlink()
        if not dry_run and removed:
            batch["pruned_at"] = now.isoformat(timespec="seconds")
            batch_file.write_text(yaml.safe_dump(batch, allow_unicode=True, sort_keys=False, width=120))
    log.info("%s %d archivos", "se borrarían" if dry_run else "borrados", len(removed))
    return removed
