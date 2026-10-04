"""Post-proceso fotográfico por "look de cámara" (parámetros en bible.yaml → camera_looks.*.post).

Todo en NumPy/Pillow: recorte al formato, softness, aberración cromática, halation, flash, curvas,
saturación, temperatura, viñeta y grano dependiente de luminancia. Salida JPEG sRGB sin EXIF, ≤ 8 MB.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

MAX_BYTES = 8 * 1024 * 1024
DEFAULTS = {"grain": 0.04, "grain_size": 1.3, "contrast": 0.05, "saturation": 1.0, "warmth": 0.0,
            "vignette": 0.1, "chroma_ab": 0.5, "halation": 0.0, "flash": 0.0, "softness": 0.3}


def crop_to_aspect(img: Image.Image, target_w: int, target_h: int, bias_y: float = 0.45) -> Image.Image:
    """Recorte centrado (levemente hacia arriba, donde suelen estar las caras) y resize final."""
    w, h = img.size
    target_ratio = target_w / target_h
    if w / h > target_ratio:
        new_w = round(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    elif w / h < target_ratio:
        new_h = round(w / target_ratio)
        top = int((h - new_h) * bias_y)
        img = img.crop((0, top, w, top + new_h))
    return img.resize((target_w, target_h), Image.LANCZOS)


def _luma(a: np.ndarray) -> np.ndarray:
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def _radial(h: int, w: int) -> np.ndarray:
    y, x = np.ogrid[:h, :w]
    return np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2) / np.sqrt(2)


def softness(img: Image.Image, amount: float) -> Image.Image:
    if amount <= 0:
        return img
    return Image.blend(img, img.filter(ImageFilter.GaussianBlur(0.6 + amount)), min(0.6, amount * 0.8))


def chromatic_aberration(a: np.ndarray, amount: float) -> np.ndarray:
    """Desplaza R hacia afuera y B hacia adentro, más fuerte en los bordes (como un lente real)."""
    if amount <= 0:
        return a
    h, w, _ = a.shape
    out = a.copy()
    for ch, sign in ((0, 1), (2, -1)):
        scale = 1 + sign * amount * 0.0015
        img = Image.fromarray((a[..., ch] * 255).astype(np.uint8))
        nw, nh = round(w * scale), round(h * scale)
        resized = np.asarray(img.resize((nw, nh), Image.BICUBIC), dtype=np.float32) / 255
        if scale > 1:
            top, left = (nh - h) // 2, (nw - w) // 2
            out[..., ch] = resized[top : top + h, left : left + w]
        else:
            pad = np.pad(resized, (((h - nh) // 2, h - nh - (h - nh) // 2), ((w - nw) // 2, w - nw - (w - nw) // 2)),
                         mode="edge")
            out[..., ch] = pad
    mask = np.clip(_radial(h, w) * 1.6, 0, 1)[..., None]
    return a * (1 - mask) + out * mask


def halation(a: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0:
        return a
    highlights = np.clip((_luma(a) - 0.75) / 0.25, 0, 1)
    glow = Image.fromarray((highlights * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(a.shape[:2]) / 120))
    glow = np.asarray(glow, dtype=np.float32)[..., None] / 255
    tint = np.array([1.0, 0.35, 0.15], dtype=np.float32)
    return np.clip(a + glow * tint * amount, 0, 1)


def flash(a: np.ndarray, amount: float) -> np.ndarray:
    """Flash frontal discreto: centro más iluminado, caída rápida hacia el fondo."""
    if amount <= 0:
        return a
    h, w, _ = a.shape
    falloff = np.clip(1 - _radial(h, w) * 1.4, 0, 1) ** 2
    return np.clip(a * (1 + amount * 0.5 * falloff[..., None]) + amount * 0.04 * falloff[..., None], 0, 1)


def tone(a: np.ndarray, contrast: float, saturation: float, warmth: float) -> np.ndarray:
    s_curve = a * a * (3 - 2 * a)                       # smoothstep: curva S suave
    a = a + contrast * (s_curve - a)
    lum = _luma(a)[..., None]
    a = lum + (a - lum) * saturation
    a = a + np.array([warmth, warmth * 0.25, -warmth], dtype=np.float32)
    a = a * 0.985 + 0.012                               # negros levemente levantados (look negativo)
    return np.clip(a, 0, 1)


def vignette(a: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0:
        return a
    h, w, _ = a.shape
    return a * (1 - amount * _radial(h, w) ** 2.2)[..., None]


def grain(a: np.ndarray, amount: float, size: float, rng: np.random.Generator) -> np.ndarray:
    """Grano tipo film: estructura con tamaño, mayor en medios tonos, mayormente monocromo."""
    if amount <= 0:
        return a
    h, w, _ = a.shape
    sh, sw = max(1, int(h / size)), max(1, int(w / size))
    def layer():
        n = rng.normal(0, 1, (sh, sw)).astype(np.float32)
        img = Image.fromarray(((n * 0.18 + 0.5).clip(0, 1) * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        return (np.asarray(img, dtype=np.float32) / 255 - 0.5) / 0.18
    mono = layer()
    lum = _luma(a)
    weight = 0.35 + 1.3 * lum * (1 - lum) * 2               # más grano en medios tonos
    noise = mono[..., None] * 0.85 + np.stack([layer() for _ in range(3)], -1) * 0.15
    return np.clip(a + noise * amount * weight[..., None], 0, 1)


def apply_look(img: Image.Image, params: dict, seed: int = 0) -> Image.Image:
    p = {**DEFAULTS, **(params or {})}
    rng = np.random.default_rng(seed)
    img = softness(img.convert("RGB"), p["softness"])
    a = np.asarray(img, dtype=np.float32) / 255
    a = chromatic_aberration(a, p["chroma_ab"])
    a = flash(a, p["flash"])
    a = halation(a, p["halation"])
    a = tone(a, p["contrast"], p["saturation"], p["warmth"])
    a = vignette(a, p["vignette"])
    a = grain(a, p["grain"], p["grain_size"], rng)
    return Image.fromarray((a * 255 + 0.5).clip(0, 255).astype(np.uint8), "RGB")


def save_jpeg(img: Image.Image, out: Path, quality: int = 92) -> Path:
    """JPEG sRGB sin metadatos (no se pasa exif/icc), bajando calidad hasta entrar en 8 MB."""
    out.parent.mkdir(parents=True, exist_ok=True)
    clean = Image.new("RGB", img.size)
    clean.paste(img.convert("RGB"))
    while True:
        buf = io.BytesIO()
        clean.save(buf, "JPEG", quality=quality, subsampling=0 if quality >= 90 else 2)
        if buf.tell() <= MAX_BYTES or quality <= 60:
            break
        quality -= 5
    out.write_bytes(buf.getvalue())
    return out


def process(src: Path, out: Path, size: tuple[int, int], look_params: dict, seed: int = 0) -> Path:
    with Image.open(src) as img:
        img = crop_to_aspect(img.convert("RGB"), *size)
    return save_jpeg(apply_look(img, look_params, seed=seed), out)
