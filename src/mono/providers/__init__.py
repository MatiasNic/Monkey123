"""Registro de proveedores de imagen."""

from __future__ import annotations

from ..config import Settings
from .base import GenerationRequest, GenerationResult, ImageProvider

__all__ = ["GenerationRequest", "GenerationResult", "ImageProvider", "get_image_provider"]


def get_image_provider(settings: Settings, name: str | None = None, dry_run: bool = False) -> ImageProvider:
    name = "mock" if dry_run else (name or settings.get("image.provider", "cloudflare"))
    if name == "mock":
        from .image_mock import MockImageProvider

        return MockImageProvider(settings)
    if name == "cloudflare":
        from .image_cloudflare import CloudflareProvider

        return CloudflareProvider(settings)
    if name == "manual":
        from .image_manual import ManualProvider

        return ManualProvider(settings)
    raise ValueError(f"image.provider desconocido: {name}")
