"""Hosting temporal de medios: la Graph API de Instagram necesita URLs públicas.

R2 (Cloudflare) vía API S3: 10 GB gratis y sin costo de egress. Los objetos se borran al publicar.
"""

from __future__ import annotations

import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path

from ..config import Settings


class MediaHost(ABC):
    name = "base"

    @abstractmethod
    def upload(self, path: Path, key: str) -> str:
        """Sube el archivo y devuelve su URL pública."""

    @abstractmethod
    def delete(self, key: str) -> None: ...


class R2Host(MediaHost):
    name = "r2"

    def __init__(self, settings: Settings):
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError('Falta boto3: pip install -e ".[publish]"') from exc
        account = settings.env("R2_ACCOUNT_ID", required=True)
        self.bucket = settings.env("R2_BUCKET", required=True)
        self.public_base = settings.env("R2_PUBLIC_BASE_URL", required=True).rstrip("/")
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.env("R2_ACCESS_KEY_ID", required=True),
            aws_secret_access_key=settings.env("R2_SECRET_ACCESS_KEY", required=True),
            region_name="auto",
        )

    def upload(self, path: Path, key: str) -> str:
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.client.upload_file(str(path), self.bucket, key, ExtraArgs={"ContentType": content_type})
        return f"{self.public_base}/{key}"

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


class DryRunHost(MediaHost):
    name = "dry-run"

    def __init__(self, settings: Settings | None = None):
        self.uploaded: list[str] = []
        self.deleted: list[str] = []

    def upload(self, path: Path, key: str) -> str:
        if not Path(path).exists():
            raise FileNotFoundError(path)
        self.uploaded.append(key)
        return f"https://media.example.invalid/{key}"

    def delete(self, key: str) -> None:
        self.deleted.append(key)


def get_media_host(settings: Settings, dry_run: bool = False) -> MediaHost:
    if dry_run:
        return DryRunHost(settings)
    name = settings.get("media_host", "r2")
    if name == "r2":
        return R2Host(settings)
    raise ValueError(f"media_host desconocido: {name}")
