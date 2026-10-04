"""Publica lo que vence en data/queue.yaml: R2 → contenedores IG → publish → historial → limpieza."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import Settings
from ..store import History, Queue, now_iso
from .instagram import (
    DryRunInstagram,
    InstagramClient,
    build_carousel_item_payload,
    build_carousel_payload,
    build_image_payload,
    build_reel_payload,
    build_story_payload,
)
from .media_host import MediaHost, get_media_host

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


def publish_entry(settings: Settings, entry: dict, client: InstagramClient, host: MediaHost) -> dict:
    """Publica una entrada de la cola. Devuelve {'media_id', 'permalink'}; siempre limpia R2."""
    ai = settings.get("instagram.ai_label", True)
    fmt = entry["format"]
    keys = []
    try:
        urls = []
        for n, file in enumerate(entry["files"], start=1):
            key = f"media/{entry['id']}/{n:02d}{Path(file).suffix}"
            urls.append(host.upload(settings.path(file), key))
            keys.append(key)
        if fmt == "carousel":
            children = [client.create_container(build_carousel_item_payload(u, entry.get("alt_text", "")))
                        for u in urls]
            for child in children:
                client.wait_ready(child)
            container = client.create_container(build_carousel_payload(children, entry.get("caption", ""), ai))
        elif fmt == "reel":
            container = client.create_container(build_reel_payload(
                urls[0], entry.get("caption", ""), ai, settings.get("instagram.share_reels_to_feed", True)))
            client.wait_ready(container, timeout=settings.get("instagram.video_poll_timeout", 900),
                              interval=settings.get("instagram.video_poll_seconds", 10))
        elif fmt == "story":
            container = client.create_container(build_story_payload(urls[0], ai))
        elif fmt == "feed":
            container = client.create_container(
                build_image_payload(urls[0], entry.get("caption", ""), entry.get("alt_text", ""), ai))
        else:
            raise ValueError(f"formato no soportado: {fmt}")
        if fmt != "reel":
            client.wait_ready(container)
        media_id = client.publish(container)
        return {"media_id": media_id, "permalink": client.permalink(media_id)}
    finally:
        for key in keys:
            try:
                host.delete(key)
            except Exception as exc:  # noqa: BLE001 — la limpieza no debe tapar el error real
                log.warning("no pude borrar %s de %s: %s", key, host.name, exc)


def publish_due(settings: Settings, now: datetime | None = None, dry_run: bool = False,
                only_id: str | None = None, client: InstagramClient | None = None,
                host: MediaHost | None = None) -> list[dict]:
    """Publica las entradas vencidas (o solo `only_id`, vencida o no). Devuelve las entradas procesadas."""
    tz = ZoneInfo(settings.get("timezone", "UTC"))
    now = now or datetime.now(tz)
    queue = Queue(settings.path("data", "queue.yaml"))
    entries = queue.load()
    if only_id:
        targets = [e for e in entries if e["id"] == only_id and e["status"] in ("queued", "failed")]
        if not targets:
            raise KeyError(f"no hay una entrada publicable con id {only_id}")
    else:
        targets = [e for e in entries if e["status"] == "queued" and datetime.fromisoformat(e["publish_at"]) <= now]
    if not targets:
        return []

    client = client or (DryRunInstagram() if dry_run else InstagramClient.from_settings(settings))
    host = host or get_media_host(settings, dry_run=dry_run)
    used, total = client.publishing_quota()
    history = History(settings.path("data", "history.jsonl"))
    done = []
    for entry in targets:
        if used >= total:
            log.warning("cuota de publicación agotada (%d/%d); quedan pendientes", used, total)
            break
        try:
            result = publish_entry(settings, entry, client, host)
        except Exception as exc:  # noqa: BLE001 — se registra en la cola
            entry["attempts"] = entry.get("attempts", 0) + 1
            entry["last_error"] = str(exc)[:500]
            if entry["attempts"] >= MAX_ATTEMPTS:
                entry["status"] = "failed"
            log.error("falló %s (intento %d): %s", entry["id"], entry["attempts"], exc)
        else:
            used += 1
            entry.update(status="published", ig_media_id=result["media_id"], permalink=result["permalink"],
                         published_at=now_iso(), last_error=None)
            log.info("publicado %s → %s", entry["id"], result["permalink"] or result["media_id"])
            if not dry_run:
                for item_id in entry["items"]:
                    try:
                        history.update(item_id, status="published", ig_media_id=result["media_id"],
                                       permalink=result["permalink"])
                    except KeyError:
                        log.warning("pieza %s no está en el historial", item_id)
        done.append(entry)
    if not dry_run:
        queue.save(entries, Queue.HEADER)
        _notify_results(settings, done)
    else:
        for name, payload in getattr(client, "calls", []):
            log.info("[dry-run] %s %s", name, payload)
    return done


def _notify_results(settings: Settings, done: list[dict]) -> None:
    from ..notify import notify

    published = [e for e in done if e["status"] == "published"]
    if published:
        notify(settings, "published", f"Publicado: {len(published)} post(s)",
               "\n".join(f"- {e['format']}: {e.get('permalink') or e['ig_media_id']}" for e in published))
    for e in done:
        if e["status"] == "failed":
            notify(settings, "failure", f"Publicación fallida: {e['id']}",
                   f"Falló {e.get('attempts')} veces. Último error: {e.get('last_error')}")
