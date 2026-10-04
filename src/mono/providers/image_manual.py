"""Modo manual asistido (gratis): arma un paquete por pieza para generar a mano en la app de Gemini /
AI Studio (o cualquier otra) y después `mono ingest` toma el resultado desde inbox/<id>.(jpg|png|webp)."""

from __future__ import annotations

from pathlib import Path
from string import Template

from .base import GenerationRequest, GenerationResult, ImageProvider

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def find_in_inbox(inbox: Path, item_id: str) -> Path | None:
    for ext in IMAGE_EXTS:
        p = inbox / f"{item_id}{ext}"
        if p.exists():
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
        rel = lambda paths: "\n".join(f"- `{p.relative_to(root) if p.is_absolute() else p}`" for p in paths)  # noqa: E731
        text = Template(self.settings.prompt_template("manual_pack")).substitute(
            item_id=req.item_id, prompt=req.prompt, ratio="4:5" if req.fmt in ("feed", "carousel") else "9:16",
            references=rel(req.references) or "- (ninguna)", scene=rel(req.scene_photos) or "- (ninguna)",
        )
        pack = pack_dir / f"{req.item_id}.md"
        pack.write_text(text)
        return GenerationResult(None, self.name, {"pack": str(pack.relative_to(root))})
