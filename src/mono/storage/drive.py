"""Copia de todo lo generado a Google Drive (carpeta "Monkey") vía un Apps Script del usuario.

Gratis y sin Google Cloud: el script (integrations/drive_apps_script.gs) corre con la cuenta del usuario y
recibe los archivos en base64. Si faltan DRIVE_WEBHOOK_URL / DRIVE_WEBHOOK_SECRET, se saltea sin romper nada.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests
import yaml

from ..config import Settings

log = logging.getLogger(__name__)
MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".mp4"}


@dataclass
class DriveUploader:
    url: str
    secret: str
    dry_run: bool = False
    http: object = requests
    uploaded: list[str] = field(default_factory=list)

    @classmethod
    def from_settings(cls, settings: Settings, dry_run: bool = False) -> "DriveUploader | None":
        if not settings.get("storage.drive.enabled", True):
            return None
        url, secret = settings.env("DRIVE_WEBHOOK_URL"), settings.env("DRIVE_WEBHOOK_SECRET")
        if not (url and secret) and not dry_run:
            log.warning("Drive: faltan DRIVE_WEBHOOK_URL / DRIVE_WEBHOOK_SECRET; no se sube nada")
            return None
        return cls(url or "https://drive.invalid", secret or "dry", dry_run=dry_run)

    def upload(self, local: Path, drive_dir: str, filename: str | None = None) -> str:
        filename = filename or local.name
        target = f"{drive_dir.strip('/')}/{filename}"
        if self.dry_run:
            self.uploaded.append(target)
            return target
        payload = {
            "secret": self.secret, "path": drive_dir, "filename": filename,
            "mimeType": mimetypes.guess_type(filename)[0] or "application/octet-stream",
            "base64": base64.b64encode(local.read_bytes()).decode(),
        }
        last_error = ""
        for attempt in range(3):
            try:
                resp = self.http.post(self.url, json=payload, timeout=60)
                data = resp.json()
                if data.get("ok"):
                    self.uploaded.append(target)
                    return data.get("url", target)
                last_error = str(data.get("error"))
                if "secret" in last_error:
                    break  # reintentar no sirve
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
            time.sleep(3 * (attempt + 1))
        raise RuntimeError(f"Drive no aceptó {target}: {last_error}")

    def upload_text(self, text: str, drive_dir: str, filename: str, tmp_dir: Path) -> str:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        path = tmp_dir / filename
        path.write_text(text)
        return self.upload(path, drive_dir, filename)


def batch_folder(batch_id: str) -> str:
    try:
        day = datetime.strptime(batch_id[:8], "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        day = "sin-fecha"
    return f"tandas/{day}_{batch_id}"


def sync_batch(settings: Settings, uploader: DriveUploader, batch_dir: Path) -> list[str]:
    """Sube aprobables (+ video), descartadas (intentos rechazados) y el resumen de una tanda."""
    batch = yaml.safe_load((batch_dir / "batch.yaml").read_text())
    base = batch_folder(batch["id"])
    done = []
    for media in sorted(p for p in batch_dir.iterdir() if p.suffix.lower() in MEDIA_EXTS):
        done.append(uploader.upload(media, f"{base}/aprobadas"))
    rejected = settings.path("output", "rejected", batch["id"])
    if rejected.is_dir():
        for media in sorted(p for p in rejected.iterdir() if p.suffix.lower() in MEDIA_EXTS):
            done.append(uploader.upload(media, f"{base}/descartadas"))
    if (batch_dir / "batch.md").exists():
        done.append(uploader.upload(batch_dir / "batch.md", base, "resumen.md"))
    manual = batch_dir / "manual"
    if manual.is_dir():
        for pack in sorted(manual.glob("*.md")):
            done.append(uploader.upload(pack, f"{base}/manual"))
    return done


def sync_published(settings: Settings, uploader: DriveUploader, entry: dict) -> list[str]:
    """Copia de un post publicado: sus archivos + un .txt con caption y link de Instagram."""
    month = (entry.get("published_at") or entry.get("publish_at") or "")[:7] or "sin-fecha"
    folder = f"publicadas/{month}"
    done = []
    for n, file in enumerate(entry.get("files") or [], start=1):
        local = settings.path(file)
        if local.exists():
            done.append(uploader.upload(local, folder, f"{entry['id']}_{n:02d}{local.suffix}"))
    info = (f"Formato: {entry.get('format')}\nPublicado: {entry.get('published_at')}\n"
            f"Instagram: {entry.get('permalink') or entry.get('ig_media_id')}\n\n{entry.get('caption') or ''}\n")
    done.append(uploader.upload_text(info, folder, f"{entry['id']}.txt", settings.path("output", "drive-tmp")))
    return done
