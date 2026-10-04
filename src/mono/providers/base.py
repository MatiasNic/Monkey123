"""Interfaz común de proveedores de imagen/video. El pipeline no sabe cuál se usa."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings

# Resolución de generación por formato (múltiplos de 16, dentro de los límites de FLUX.2).
GEN_SIZES = {"feed": (1024, 1280), "carousel": (1024, 1280), "story": (864, 1536), "reel": (864, 1536)}


@dataclass
class GenerationRequest:
    item_id: str
    prompt: str
    fmt: str
    references: list[Path]            # identidad del personaje (character/reference)
    scene_photos: list[Path] = field(default_factory=list)
    seed: int | None = None

    @property
    def size(self) -> tuple[int, int]:
        return GEN_SIZES.get(self.fmt, GEN_SIZES["feed"])


@dataclass
class GenerationResult:
    path: Path | None                 # None = pendiente (p. ej. proveedor manual)
    provider: str
    meta: dict = field(default_factory=dict)


class ImageProvider(ABC):
    name = "base"
    automatic = True                  # False = requiere intervención humana

    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    def generate(self, req: GenerationRequest, out_dir: Path) -> GenerationResult: ...


class VideoProvider(ABC):
    name = "base"

    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    def generate(self, images: list[Path], out_path: Path, **opts) -> Path: ...
