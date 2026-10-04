"""Aprobación de tandas mergeadas y armado de la cola de publicación (data/queue.yaml)."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .captions.writer import full_text
from .config import Settings
from .pipeline import load_batch, save_batch, write_review
from .store import History, Queue

log = logging.getLogger(__name__)
HORIZON_DAYS = 120


def _tz(settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.get("timezone", "UTC"))


def _slot_time(settings: Settings, fmt: str) -> time:
    raw = settings.get("schedule.story_time" if fmt == "story" else "schedule.publish_time", "19:00")
    hh, mm = (int(x) for x in str(raw).split(":"))
    return time(hh, mm)


def next_slot(settings: Settings, fmt: str, taken: set[tuple[str, date]], now: datetime | None = None) -> datetime:
    """Primer día libre (sin otra pieza del mismo formato) cuyo día de semana esté en schedule.slots[fmt]."""
    tz = _tz(settings)
    now = now or datetime.now(tz)
    days = settings.get(f"schedule.slots.{fmt}") or settings.get("schedule.slots.feed") or [0, 2, 4]
    at = _slot_time(settings, fmt)
    for offset in range(HORIZON_DAYS):
        day = now.date() + timedelta(days=offset)
        when = datetime.combine(day, at, tzinfo=tz)
        if day.weekday() in days and (fmt, day) not in taken and when > now:
            return when
    raise RuntimeError(f"no hay lugar en la cola para {fmt} en {HORIZON_DAYS} días")


def taken_slots(queue_items: list[dict]) -> set[tuple[str, date]]:
    out = set()
    for entry in queue_items:
        if entry.get("status") in ("queued", "published"):
            out.add((entry["format"], datetime.fromisoformat(entry["publish_at"]).date()))
    return out


def _posts_for_batch(batch: dict) -> list[tuple[str, list[dict]]]:
    approved = [i for i in batch["items"] if i["status"] == "approved"]
    if not approved:
        return []
    if batch["format"] == "carousel":
        if len(approved) >= 2:
            return [("carousel", approved[:10])]
        return [("feed", approved)]  # si quedó una sola, sale como post simple
    return [(batch["format"], [item]) for item in approved]


def approve_batches(settings: Settings, folders: list[Path] | None = None, now: datetime | None = None,
                    dry_run: bool = False) -> list[dict]:
    """Marca como aprobadas las piezas `draft` de las tandas (mergeadas) y las encola.

    Si el revisor borró el .jpg de una pieza en el PR, esa pieza queda `discarded`.
    """
    queue = Queue(settings.path("data", "queue.yaml"))
    history = History(settings.path("data", "history.jsonl"))
    entries = queue.load()
    taken = taken_slots(entries)
    created = []
    folders = folders or sorted(p.parent for p in settings.path("drafts").glob("*/batch.yaml"))
    for folder in folders:
        batch = load_batch(folder)
        changed = False
        for item in batch["items"]:
            if item["status"] != "draft":
                continue
            final = (item.get("files") or {}).get("final")
            if not final or not settings.path(final).exists():
                item.update(status="discarded", discard_reason="descartada en la revisión del PR")
            else:
                item["status"] = "approved"
            changed = True
        for fmt, items in _posts_for_batch(batch):
            when = next_slot(settings, fmt, taken, now)
            taken.add((fmt, when.date()))
            caption = batch.get("caption") if fmt == "carousel" else items[0].get("caption")
            entry = {
                "id": f"post-{items[0]['id']}",
                "format": fmt,
                "items": [i["id"] for i in items],
                "files": [i["files"]["final"] for i in items],
                "caption": full_text(settings, caption) if fmt != "story" else "",
                "alt_text": (caption or {}).get("alt_text", ""),
                "publish_at": when.isoformat(),
                "status": "queued",
                "ig_media_id": None,
            }
            entries.append(entry)
            created.append(entry)
            for item in items:
                item["status"] = "queued"
                item["queue_id"] = entry["id"]
        if changed and not dry_run:
            save_batch(folder, batch)
            write_review(settings, batch, folder)
            for item in batch["items"]:
                fields = {k: item.get(k) for k in ("status", "discard_reason", "queue_id")}
                try:
                    history.update(item["id"], **fields)
                except KeyError:
                    history.append([item])
    if created and not dry_run:
        entries.sort(key=lambda e: e["publish_at"])
        queue.save(entries, Queue.HEADER)
    for entry in created:
        log.info("encolado %s (%s, %d img) para %s", entry["id"], entry["format"], len(entry["files"]),
                 entry["publish_at"])
    return created


def due_posts(settings: Settings, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(_tz(settings))
    entries = Queue(settings.path("data", "queue.yaml")).load()
    return [e for e in entries if e["status"] == "queued" and datetime.fromisoformat(e["publish_at"]) <= now]


def plan_for_today(settings: Settings, today: date | None = None) -> list[dict]:
    """Tandas a generar hoy según config.generate_plan (para la matrix del workflow)."""
    today = today or datetime.now(ZoneInfo("UTC")).date()
    key = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[today.weekday()]
    return list(settings.get(f"generate_plan.{key}") or [])
