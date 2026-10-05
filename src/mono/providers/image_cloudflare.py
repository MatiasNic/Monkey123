"""Cloudflare Workers AI — FLUX.2 con imágenes de referencia (tier gratis: 10k neuronas/día).

API: multipart/form-data con `prompt`, `input_image_0..3` (cada una < 512x512), width, height, steps, seed.
Respuesta: {"result": {"image": "<base64>"}, "success": true}.
"""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path

import requests
from PIL import Image

from .base import GenerationRequest, GenerationResult, ImageProvider, QuotaExhausted

API = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
MAX_INPUTS = 4
MAX_INPUT_SIDE = 511


def is_quota_exhausted(status: int, text: str) -> bool:
    """429 con código 4006: se terminó la asignación diaria gratis (10.000 neuronas)."""
    return status == 429 and ("4006" in text or "daily free allocation" in text)


def shrink_for_input(path: Path) -> bytes:
    img = Image.open(path).convert("RGB")
    img.thumbnail((MAX_INPUT_SIDE, MAX_INPUT_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def compose_prompt(req: GenerationRequest, n_scene: int, n_refs: int) -> str:
    """Le explica al modelo qué es cada imagen de entrada por índice."""
    lines = []
    idx = 0
    if n_scene:
        lines.append(f"Image {idx} is the real location: reproduce this exact place, architecture, furniture, "
                     "light and perspective.")
        idx += n_scene
    if n_refs:
        ids = ", ".join(str(i) for i in range(idx, idx + n_refs))
        lines.append(f"Images {ids} show the character: the same macaque must appear with identical face, fur "
                     "colour and proportions (ignore their clothes, poses and backgrounds).")
    return "\n".join(lines + ["", req.prompt])


class CloudflareProvider(ImageProvider):
    name = "cloudflare"

    def __init__(self, settings):
        super().__init__(settings)
        self.account = settings.env("CLOUDFLARE_ACCOUNT_ID", required=True)
        self.token = settings.env("CLOUDFLARE_API_TOKEN", required=True)
        self.model = settings.get("image.cloudflare_model", "@cf/black-forest-labs/flux-2-klein-9b")
        self.steps = settings.get("image.steps")

    def build_form(self, req: GenerationRequest) -> tuple[dict, dict]:
        scene = req.scene_photos[:1]
        refs = req.references[: MAX_INPUTS - len(scene)]
        width, height = req.size
        data = {"prompt": compose_prompt(req, len(scene), len(refs)), "width": str(width), "height": str(height)}
        if req.seed is not None:
            data["seed"] = str(req.seed)
        if self.steps:
            data["steps"] = str(self.steps)
        files = {f"input_image_{i}": (p.name, shrink_for_input(p), "image/jpeg") for i, p in enumerate(scene + refs)}
        return data, files

    def generate(self, req: GenerationRequest, out_dir: Path) -> GenerationResult:
        data, files = self.build_form(req)
        url = API.format(account=self.account, model=self.model)
        for attempt in range(3):
            resp = requests.post(url, headers={"Authorization": f"Bearer {self.token}"}, data=data, files=files,
                                 timeout=300)
            if is_quota_exhausted(resp.status_code, resp.text):
                raise QuotaExhausted(f"Cloudflare: cuota diaria agotada ({resp.text[:200]})")
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            break
        if resp.status_code != 200:
            raise RuntimeError(f"Cloudflare {resp.status_code}: {resp.text[:500]}")
        payload = resp.json()
        image_b64 = (payload.get("result") or {}).get("image")
        if not payload.get("success", True) or not image_b64:
            raise RuntimeError(f"Cloudflare sin imagen: {str(payload)[:500]}")
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{req.item_id}.png"
        Image.open(io.BytesIO(base64.b64decode(image_b64))).save(out)
        return GenerationResult(out, self.name, {"model": self.model, "seed": req.seed})
