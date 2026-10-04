"""Proveedor falso para --dry-run/tests: imagen sintética 'fotográfica' sin red."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .base import GenerationRequest, GenerationResult, ImageProvider


class MockImageProvider(ImageProvider):
    name = "mock"

    def generate(self, req: GenerationRequest, out_dir: Path) -> GenerationResult:
        seed = int(hashlib.sha1(req.item_id.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        w, h = req.size
        top, bottom = rng.integers(40, 220, 3), rng.integers(20, 160, 3)
        t = np.linspace(0, 1, h)[:, None, None]
        arr = (top * (1 - t) + bottom * t).repeat(w, axis=1)
        img = Image.fromarray(arr.astype(np.uint8))
        draw = ImageDraw.Draw(img)
        for _ in range(12):  # "objetos" de la escena
            x, y = rng.integers(0, w), rng.integers(0, h)
            s = int(rng.integers(40, 260))
            draw.ellipse([x, y, x + s, y + s * 1.2], fill=tuple(int(c) for c in rng.integers(0, 255, 3)))
        cx, cy = w // 2, int(h * 0.6)  # silueta del "mono"
        draw.ellipse([cx - 90, cy - 260, cx + 90, cy - 80], fill=(140, 105, 70))
        draw.rounded_rectangle([cx - 140, cy - 90, cx + 140, cy + 220], 60, fill=(235, 235, 230))
        img = img.filter(ImageFilter.GaussianBlur(2))
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{req.item_id}.png"
        img.save(out)
        return GenerationResult(out, self.name, {"seed": seed})
