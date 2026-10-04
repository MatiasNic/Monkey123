"""Construye el prompt de imagen a partir de la biblia + idea + look + escena."""

from __future__ import annotations

from string import Template

import yaml

from ..config import Settings


def scene_notes(settings: Settings, scene: str | None) -> tuple[str, list]:
    if not scene:
        return "", []
    folder = settings.path("scenes", scene)
    meta = {}
    if (folder / "scene.yaml").exists():
        meta = yaml.safe_load((folder / "scene.yaml").read_text()) or {}
    photos = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    notes = (
        "Use the provided location photo as the exact setting: keep its architecture, layout, furniture, "
        "lighting and perspective recognisable, and integrate the macaque naturally as if photographed there. "
    )
    if meta.get("description"):
        notes += meta["description"].strip() + " "
    if meta.get("keep"):
        notes += "Keep: " + ", ".join(meta["keep"]) + "."
    return notes.strip(), photos


def build_image_prompt(settings: Settings, idea: dict) -> dict:
    """Devuelve {'prompt', 'references', 'scene_photos', 'size'} listo para cualquier provider."""
    bible = settings.bible
    look = bible["camera_looks"][idea["camera_look"]]
    fmt = bible["formats"]["carousel" if idea["format"] == "carousel" else idea["format"]]
    notes, photos = scene_notes(settings, idea.get("scene"))
    accessories = [a for a in idea.get("accessories") or [] if a and a != "none"]
    prompt = Template(settings.prompt_template("image_prompt")).substitute(
        description=idea.get("description", "").strip(),
        identity_desc=" ".join(bible["identity"]["description"].split()),
        pose=idea.get("pose", ""),
        expression=idea.get("expression", ""),
        gaze=idea.get("gaze", ""),
        outfit=idea.get("outfit", ""),
        accessories=(", with " + ", ".join(accessories)) if accessories else "",
        location=idea.get("location", ""),
        scene_notes=notes,
        lighting=idea.get("lighting", ""),
        camera_distance=idea.get("camera_distance", ""),
        ratio=fmt["ratio"],
        look_prompt=look["prompt"],
        always=bible["photography"]["always"],
        avoid=bible["photography"]["avoid"],
    )
    prompt = "\n".join(line.rstrip() for line in prompt.splitlines()).replace("\n\n\n", "\n\n").strip()
    return {
        "prompt": prompt,
        "references": [str(p.relative_to(settings.root)) for p in settings.reference_images()],
        "scene_photos": [str(p.relative_to(settings.root)) for p in photos],
        "size": fmt["size"],
    }
