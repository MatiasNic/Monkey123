"""Carga de configuración: config.yaml + bible.yaml + variables de entorno (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import yaml


def find_root(start: Path | None = None) -> Path:
    """Raíz del repo: MONO_ROOT o el primer ancestro con config.yaml."""
    if env := os.environ.get("MONO_ROOT"):
        return Path(env).resolve()
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / "config.yaml").exists():
            return p
    raise FileNotFoundError("No encontré config.yaml; corré desde el repo o definí MONO_ROOT")


def load_dotenv(path: Path) -> None:
    """Parser mínimo de .env (no pisa variables ya definidas)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


@dataclass
class Settings:
    root: Path
    data: dict = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path | None = None) -> "Settings":
        root = root or find_root()
        load_dotenv(root / ".env")
        data = yaml.safe_load((root / "config.yaml").read_text()) or {}
        return cls(root=root, data=data)

    def get(self, dotted: str, default=None):
        cur = self.data
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    @cached_property
    def bible(self) -> dict:
        return yaml.safe_load((self.root / "character" / "bible.yaml").read_text())

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    def reference_images(self) -> list[Path]:
        ref = self.root / self.bible["identity"]["reference_dir"]
        return sorted(p for p in ref.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})

    def generator_references(self) -> list[Path]:
        """Referencias que recibe el generador: los recortes si existen, si no las referencias completas."""
        crops = self.bible["identity"].get("generator_refs_dir")
        folder = self.root / crops if crops else None
        if folder and folder.is_dir():
            found = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
            if found:
                return found
        return self.reference_images()

    def prompt_template(self, name: str) -> str:
        return (self.root / "prompts" / f"{name}.md").read_text()

    @staticmethod
    def env(key: str, required: bool = False) -> str:
        value = os.environ.get(key, "")
        if required and not value:
            raise RuntimeError(f"Falta la variable de entorno {key} (ver .env.example)")
        return value
