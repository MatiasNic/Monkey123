"""QC con visión: Claude compara la candidata con las referencias del personaje y devuelve JSON."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from string import Template

from PIL import Image

from ..config import Settings
from ..llm.base import LLM
from .heuristics import check_image

QC_SIDE = 1024  # se achica la candidata para gastar menos contexto


@dataclass
class QCResult:
    passed: bool
    score: float
    reasons: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _downscale(path: Path, tmpdir: Path) -> Path:
    img = Image.open(path).convert("RGB")
    img.thumbnail((QC_SIDE, QC_SIDE), Image.LANCZOS)
    out = tmpdir / f"candidate_{path.stem}.jpg"
    img.save(out, "JPEG", quality=88)
    return out


def evaluate(settings: Settings, llm: LLM, image: Path, item: dict) -> QCResult:
    heur = check_image(image)
    if not heur.ok:
        return QCResult(False, 0.0, heur.issues, {"heuristics": heur.seams})
    refs = settings.reference_images()
    idea = {k: item.get(k) for k in ("description", "location", "activity", "pose", "outfit", "lighting",
                                     "camera_distance", "camera_look")}
    with tempfile.TemporaryDirectory() as tmp:
        candidate = _downscale(image, Path(tmp))
        prompt = Template(settings.prompt_template("qc")).substitute(
            n_refs=len(refs),
            idea=json.dumps(idea, ensure_ascii=False, indent=1),
            identity=" ".join(settings.bible["identity"]["description"].split()),
        )
        data = llm.complete_json(prompt, images=[*refs, candidate], task="qc", context={"item": item})
    threshold = settings.get("qc.pass_score", 7.0)
    score = float(data.get("score", 0))
    hard_fail = [k for k in ("is_collage", "has_text") if data.get(k)]
    if data.get("species_ok") is False:
        hard_fail.append("species")
    reasons = list(data.get("reasons") or [])
    if hard_fail:
        reasons.insert(0, f"falla dura: {hard_fail}")
    passed = score >= threshold and not hard_fail
    return QCResult(passed, score, reasons, {k: v for k, v in data.items() if k not in ("reasons",)})
