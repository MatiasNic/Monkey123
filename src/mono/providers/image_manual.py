"""Modo híbrido (gratis): arma un paquete por pieza para generarla a mano en la app de Gemini (o AI Studio)
con las fotos de referencia del personaje, y después `mono ingest` toma el resultado desde inbox/."""

from __future__ import annotations

import re
from pathlib import Path
from string import Template

from .base import GenerationRequest, GenerationResult, ImageProvider

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# Encabezado que va antes del prompt cuando se pega en Gemini junto con las fotos de referencia.
MANUAL_PREFIX = (
    "The attached photos show the character: always this same real macaque. Copy his face exactly "
    "(round face, puffy cheeks, heavy half-closed eyelids, short flat muzzle, small pursed mouth, fluffy fur "
    "framing the face), his fur and his proportions. Ignore their clothes and backgrounds. "
    "If a location photo is attached, use it as the exact setting. Generate ONE single photo, not a collage."
)


def manual_prompt(prompt: str) -> str:
    return f"{MANUAL_PREFIX}\n\n{prompt}"


def item_number(item_id: str) -> str:
    """'20261010-0133-ba73-02' → '02'."""
    return item_id.rsplit("-", 1)[-1]


def _short_match(stem: str, number: str) -> bool:
    """Nombres cortos que acepta inbox/: '02', '2', 'foto-02', 'mono_2', 'IMG 02'…"""
    stem = stem.strip().lower()
    n = str(int(number)) if number.isdigit() else number
    if stem in (number, n):
        return True
    return bool(re.search(rf"(^|[\s_-])0*{re.escape(n)}$", stem))


def find_in_inbox(inbox: Path, item_id: str, allow_short: bool = False) -> Path | None:
    """Busca inbox/<id>.<ext>; con allow_short también acepta el número de la pieza (inbox/02.jpg)."""
    if not inbox.is_dir():
        return None
    for ext in IMAGE_EXTS:
        p = inbox / f"{item_id}{ext}"
        if p.exists():
            return p
    if allow_short:
        number = item_number(item_id)
        for p in sorted(inbox.iterdir()):
            if p.suffix.lower() in IMAGE_EXTS and _short_match(p.stem, number):
                return p
    return None


class ManualProvider(ImageProvider):
    name = "manual"
    automatic = False

    def generate(self, req: GenerationRequest, out_dir: Path) -> GenerationResult:
        inbox = self.settings.path("inbox")
        if found := find_in_inbox(inbox, req.item_id):
            return GenerationResult(found, self.name, {"source": "inbox"})
        pack_dir = out_dir / "manual"
        pack_dir.mkdir(parents=True, exist_ok=True)
        root = self.settings.root
        # Para Gemini van las fotos de referencia completas: es la cara que tiene que copiar.
        refs = [str(p.relative_to(root)) for p in self.settings.reference_images()]
        scene = [str(p.relative_to(root) if p.is_absolute() else p) for p in req.scene_photos]
        bullets = lambda paths: "\n".join(f"   - `{p}`" for p in paths) or "   - (ninguna)"  # noqa: E731
        text = Template(self.settings.prompt_template("manual_pack")).substitute(
            item_id=req.item_id, number=item_number(req.item_id),
            prompt=manual_prompt(req.prompt), ratio="4:5" if req.fmt in ("feed", "carousel") else "9:16",
            references=bullets(refs), scene=bullets(scene),
        )
        pack = pack_dir / f"{req.item_id}.md"
        pack.write_text(text)
        return GenerationResult(None, self.name, {"pack": str(pack.relative_to(root)), "refs": refs + scene})
