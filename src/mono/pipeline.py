"""Orquestación de una tanda: ideas → prompts → (imágenes → QC → post-proceso → captions)."""

from __future__ import annotations

import hashlib
import logging
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .captions.writer import write_caption
from .config import Settings
from .ideation.ideas import generate_ideas
from .llm import get_llm
from .llm.base import LLM
from .postprocess.looks import process
from .prompting.builder import build_image_prompt
from .providers import GenerationRequest, ImageProvider, get_image_provider
from .providers.image_manual import find_in_inbox
from .qc.vision_qc import evaluate
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


# ---------------------------------------------------------------------------
# Render: imagen → QC → post-proceso
# ---------------------------------------------------------------------------

def _seed(item_id: str, attempt: int) -> int:
    return (int(hashlib.sha1(item_id.encode()).hexdigest()[:8], 16) + attempt * 7919) % 2**31


def _request(settings: Settings, item: dict, attempt: int) -> GenerationRequest:
    return GenerationRequest(
        item_id=item["id"], prompt=item["prompt"], fmt=item["format"],
        references=[settings.path(p) for p in item.get("references") or []],
        scene_photos=[settings.path(p) for p in item.get("scene_photos") or []],
        seed=_seed(item["id"], attempt),
    )


def finalize(settings: Settings, item: dict, raw: Path, out_dir: Path) -> Path:
    look = settings.bible["camera_looks"][item["camera_look"]]
    final = out_dir / f"{item['id']}.jpg"
    process(raw, final, tuple(item["size"]), look.get("post", {}), seed=_seed(item["id"], 0))
    return final


def render_item(settings: Settings, item: dict, provider: ImageProvider, llm: LLM, out_dir: Path,
                raw_dir: Path) -> dict:
    """Genera hasta image.max_attempts veces hasta pasar el QC. Actualiza `item` in place."""
    max_attempts = settings.get("image.max_attempts", 3) if provider.automatic else 1
    item["provider"] = provider.name
    attempts = []
    for attempt in range(1, max_attempts + 1):
        try:
            result = provider.generate(_request(settings, item, attempt), raw_dir)
        except Exception as exc:  # noqa: BLE001 — se registra y se reintenta
            log.warning("%s intento %d: error del proveedor: %s", item["id"], attempt, exc)
            attempts.append({"attempt": attempt, "error": str(exc)[:300]})
            continue
        if result.path is None:  # manual: queda esperando la imagen en inbox/
            item["status"] = "awaiting_manual"
            item["files"] = {"manual_pack": result.meta.get("pack")}
            return item
        qc = evaluate(settings, llm, result.path, item)
        attempts.append({"attempt": attempt, "score": qc.score, "passed": qc.passed, "reasons": qc.reasons[:4]})
        log.info("%s intento %d: QC %.1f %s", item["id"], attempt, qc.score, "OK" if qc.passed else qc.reasons[:2])
        if qc.passed:
            final = finalize(settings, item, result.path, out_dir)
            item.update(status="draft", qc=qc.to_dict(), qc_attempts=attempts,
                        files={"raw": _rel(settings, result.path), "final": _rel(settings, final)})
            return item
        rejected = settings.path("output", "rejected", item["batch"])
        rejected.mkdir(parents=True, exist_ok=True)
        shutil.move(str(result.path), rejected / f"{item['id']}_a{attempt}{result.path.suffix}")
    item.update(status="discarded", qc_attempts=attempts,
                discard_reason=f"no pasó el QC en {max_attempts} intento(s)")
    return item


def _rel(settings: Settings, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(settings.root))
    except ValueError:
        return str(path)


def render_batch(settings: Settings, batch: dict, provider_name: str | None = None, dry_run: bool = False) -> dict:
    provider = get_image_provider(settings, provider_name, dry_run=dry_run)
    llm = get_llm(settings, dry_run=dry_run)
    out_dir = settings.path(batch["dir"])
    raw_dir = settings.path("output", "raw", batch["id"])
    for item in batch["items"]:
        render_item(settings, item, provider, llm, out_dir, raw_dir)
    add_captions(settings, batch, llm)
    build_reel(settings, batch)
    _persist(settings, batch, dry_run)
    return batch


SEQUENCE_FORMATS = ("carousel", "reel")


def build_reel(settings: Settings, batch: dict, items: list[dict] | None = None, force: bool = False) -> Path | None:
    """Arma el video del reel con las piezas listas (o `items`). No hace nada si faltan piezas manuales."""
    if batch["format"] != "reel":
        return None
    if items is None:
        if any(i["status"] == "awaiting_manual" for i in batch["items"]):
            return None
        items = [i for i in batch["items"] if i["status"] == "draft"]
    ids = [i["id"] for i in items]
    current = batch.get("video") or {}
    if len(items) < 2 or (current.get("items") == ids and not force):
        return None
    from .providers.video_slideshow import get_video_provider

    out = settings.path(batch["dir"], f"{batch['id']}.mp4")
    get_video_provider(settings).generate([settings.path(i["files"]["final"]) for i in items], out, seed=batch["id"])
    batch["video"] = {"file": _rel(settings, out), "items": ids}
    log.info("reel %s: %d imágenes → %s", batch["id"], len(ids), out)
    return out


def add_captions(settings: Settings, batch: dict, llm: LLM) -> None:
    """Feed/reel: un caption por pieza. Carrusel: uno para todo el posteo. Historias: sin caption."""
    if batch["format"] == "story":
        return
    ready = [i for i in batch["items"] if i["status"] == "draft"]
    if batch["format"] in SEQUENCE_FORMATS:
        pending = any(i["status"] == "awaiting_manual" for i in batch["items"])
        if ready and not pending and not batch.get("caption"):
            batch["caption"] = write_caption(settings, llm, ready)
            for item in ready:
                item["caption"] = batch["caption"]
        return
    for item in ready:
        if not item.get("caption"):
            item["caption"] = write_caption(settings, llm, [item])


def ingest(settings: Settings, batch_dirs: list[Path] | None = None, force: bool = False,
           dry_run: bool = False) -> list[dict]:
    """Toma imágenes manuales de inbox/<id>.* para piezas en awaiting_manual: QC → post-proceso."""
    llm = get_llm(settings, dry_run=dry_run)
    inbox = settings.path("inbox")
    done = []
    folders = batch_dirs or sorted(p.parent for p in settings.path("drafts").glob("*/batch.yaml"))
    for folder in folders:
        batch = load_batch(folder)
        changed = False
        for item in batch["items"]:
            if item.get("status") not in ("awaiting_manual", "qc_failed"):
                continue
            src = find_in_inbox(inbox, item["id"])
            if not src:
                continue
            raw_dir = settings.path("output", "raw", batch["id"])
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw = raw_dir / src.name
            shutil.copy(src, raw)
            qc = evaluate(settings, llm, raw, item)
            item["qc"] = qc.to_dict()
            if qc.passed or force:
                final = finalize(settings, item, raw, folder)
                item.update(status="draft", files={**item.get("files", {}), "raw": _rel(settings, raw),
                                                   "final": _rel(settings, final)})
                if not dry_run:
                    src.unlink()
            else:
                item["status"] = "qc_failed"
            log.info("ingest %s: QC %.1f → %s", item["id"], qc.score, item["status"])
            done.append(item)
            changed = True
        if changed:
            add_captions(settings, batch, llm)
            build_reel(settings, batch)
            _persist(settings, batch, dry_run)
    return done


def _persist(settings: Settings, batch: dict, dry_run: bool) -> None:
    folder = settings.path(batch["dir"])
    save_batch(folder, batch)
    write_review(settings, batch, folder)
    if dry_run:
        return
    history = History(settings.path("data", "history.jsonl"))
    for item in batch["items"]:
        fields = {k: item.get(k) for k in ("status", "provider", "files", "qc", "caption", "discard_reason")}
        try:
            history.update(item["id"], **fields)
        except KeyError:
            history.append([item])


def write_review(settings: Settings, batch: dict, folder: Path) -> Path:
    """batch.md: resumen legible para revisar la tanda en el PR."""
    path = folder / "batch.md"
    path.write_text(review_markdown(batch))
    return path


def review_markdown(batch: dict, image_base: str = "") -> str:
    """Markdown de la tanda. `image_base` = URL base para que las imágenes se vean en el cuerpo del PR."""
    lines = [f"# Tanda {batch['id']}", "",
             f"Formato: **{batch['format']}** · Escena: {batch.get('scene') or '—'} · Tema: {batch.get('theme') or '—'}",
             ""]
    for item in batch["items"]:
        lines.append(f"## {item['id']} — {item['status']}")
        final = (item.get("files") or {}).get("final")
        if final:
            src = f"{image_base.rstrip('/')}/{final}" if image_base else Path(final).name
            lines.append(f'<img src="{src}" width="320" alt="{item["id"]}">  ')
        lines.append(f"**Idea:** {item.get('concept_es') or item.get('concept')}  ")
        lines.append(f"**Look:** `{item['camera_look']}` · {item.get('location')} · {item.get('pose')} · "
                     f"{item.get('lighting')}  ")
        if item.get("qc"):
            lines.append(f"**QC:** {item['qc']['score']:.1f} — {'; '.join(item['qc'].get('reasons', [])[:3])}  ")
        if item.get("caption"):
            cap = item["caption"]
            lines.append(f"**Caption:** {cap.get('caption')}  ")
            lines.append(f"**Hashtags:** {' '.join(cap.get('hashtags', []))}  ")
        if item["status"] == "awaiting_manual":
            lines.append(f"**Pendiente manual:** ver `{(item.get('files') or {}).get('manual_pack')}` "
                         f"y subir `inbox/{item['id']}.jpg`")
        if item.get("discard_reason"):
            lines.append(f"**Descartada:** {item['discard_reason']}")
        lines.append("")
    if batch.get("video"):
        video = batch["video"]["file"]
        src = f"{image_base.rstrip('/')}/{video}" if image_base else Path(video).name
        lines[3:3] = [f"**Video del reel:** [{Path(video).name}]({src}) ({len(batch['video']['items'])} imágenes)", ""]
    if batch.get("format") in SEQUENCE_FORMATS and batch.get("caption"):
        lines[3:3] = [f"**Caption del {'reel' if batch['format'] == 'reel' else 'carrusel'}:** "
                      f"{batch['caption']['caption']}  ",
                      f"**Hashtags:** {' '.join(batch['caption'].get('hashtags', []))}", ""]
    lines += ["---", "Para descartar una pieza: borrá su .jpg en este PR antes de mergear. "
              "Mergear = aprobar; las piezas restantes entran a la cola de publicación."]
    return "\n".join(lines)
