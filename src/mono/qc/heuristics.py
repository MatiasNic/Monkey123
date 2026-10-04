"""Chequeos gratis y locales previos al QC con visión: collage/grilla, imagen vacía, tamaño."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

ANALYSIS_SIDE = 1024


@dataclass
class HeuristicReport:
    ok: bool
    issues: list[str] = field(default_factory=list)
    seams: dict = field(default_factory=dict)


def _load_gray(path: Path) -> np.ndarray:
    img = Image.open(path).convert("L")
    img.thumbnail((ANALYSIS_SIDE, ANALYSIS_SIDE), Image.LANCZOS)
    return np.asarray(img, dtype=np.float32) / 255.0


def _seam_positions(gray: np.ndarray, axis: int, margin: float = 0.12) -> list[float]:
    """Líneas rectas que cruzan TODA la imagen (bordes entre paneles) en la zona interior.

    axis=0 → busca líneas horizontales (diferencias entre filas); axis=1 → verticales.
    Un corte entre paneles es una discontinuidad: la diferencia en esa línea es mucho mayor que en las
    vecinas y aparece en casi todo el largo de la línea (un borde natural rara vez cumple las dos).
    """
    diff = np.abs(np.diff(gray, axis=axis))
    line_mean = diff.mean(axis=1 - axis)
    coverage = (diff > 0.06).mean(axis=1 - axis)
    n = line_mean.shape[0]
    lo, hi = int(n * margin), int(n * (1 - margin))
    seams = []
    for i in range(lo, hi):
        window = np.r_[line_mean[max(0, i - 6) : max(0, i - 1)], line_mean[i + 2 : i + 7]]
        local = float(np.median(window)) if window.size else 0.0
        if line_mean[i] > 0.05 and line_mean[i] > 2.2 * max(local, 0.004) and coverage[i] > 0.6:
            seams.append(i / n)
    # Banda lisa (gutter) que cruza todo, flanqueada por contenido con textura (no un cielo liso).
    texture = gray.std(axis=1 - axis)
    gutters = [i / n for i in range(lo, hi)
               if texture[i] < 0.006 and texture[max(0, i - 8)] > 0.05 and texture[min(n - 1, i + 8)] > 0.05]
    return _cluster(seams) + _cluster(gutters)


def _cluster(positions: list[float], gap: float = 0.02) -> list[float]:
    out: list[float] = []
    for p in positions:
        if not out or p - out[-1] > gap:
            out.append(p)
    return out


def check_image(path: Path, min_side: int = 600) -> HeuristicReport:
    issues = []
    with Image.open(path) as img:
        w, h = img.size
    if min(w, h) < min_side:
        issues.append(f"resolución baja ({w}x{h})")
    gray = _load_gray(path)
    if gray.std() < 0.03:
        issues.append("imagen casi uniforme / vacía")
    horizontal = _seam_positions(gray, axis=0)
    vertical = _seam_positions(gray, axis=1)
    if horizontal or vertical:
        issues.append(f"posible collage/grilla: cortes horizontales {horizontal} verticales {vertical}")
    return HeuristicReport(not issues, issues, {"horizontal": horizontal, "vertical": vertical})
