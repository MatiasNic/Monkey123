"""Reels gratis: slideshow con movimiento sutil (Ken Burns) y fundidos, armado con ffmpeg.

Salida compatible con Reels: MP4 H.264 4:2:0, 30 fps, moov al frente (faststart), AAC 48 kHz.
Si hay pistas en `video.audio_dir` se usa una (elegida de forma determinista); si no, pista silenciosa.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from .base import VideoProvider

AUDIO_EXTS = (".mp3", ".m4a", ".aac", ".wav")
MOVES = ("zoom_in", "zoom_out", "pan_right", "pan_left", "pan_up")


def _move_exprs(move: str, frames: int, amount: float) -> tuple[str, str, str]:
    """Expresiones zoompan (z, x, y) para cada tipo de movimiento. `on` = frame actual."""
    p = f"(on/{frames})"
    center_x, center_y = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    if move == "zoom_in":
        return f"1+{amount}*{p}", center_x, center_y
    if move == "zoom_out":
        return f"{1 + amount}-{amount}*{p}", center_x, center_y
    z = f"{1 + amount}"
    if move == "pan_right":
        return z, f"(iw-iw/zoom)*{p}", center_y
    if move == "pan_left":
        return z, f"(iw-iw/zoom)*(1-{p})", center_y
    return z, center_x, f"(ih-ih/zoom)*(1-{p})"  # pan_up


def build_command(images: list[Path], out: Path, size=(1080, 1920), fps: int = 30, seconds_per_image: float = 2.5,
                  fade: float = 0.4, zoom: float = 0.08, audio: Path | None = None, seed: str = "") -> list[str]:
    if len(images) < 2:
        raise ValueError("un reel slideshow necesita al menos 2 imágenes")
    w, h = size
    clip = seconds_per_image + fade
    frames = round(clip * fps)
    total = len(images) * seconds_per_image + fade
    start = int(hashlib.sha1(seed.encode()).hexdigest()[:4], 16) if seed else 0

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for img in images:
        cmd += ["-i", str(img)]
    if audio:
        cmd += ["-i", str(audio)]
    else:
        cmd += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]

    chains = []
    for i in range(len(images)):
        z, x, y = _move_exprs(MOVES[(start + i) % len(MOVES)], frames, zoom)
        # Se escala al doble antes del zoompan para evitar el temblor por redondeo de píxeles.
        chains.append(
            f"[{i}:v]scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},setsar=1,format=yuv420p[v{i}]"
        )
    last = "v0"
    for i in range(1, len(images)):
        label = f"x{i}"
        chains.append(f"[{last}][v{i}]xfade=transition=fade:duration={fade}:offset={i * seconds_per_image:.3f}[{label}]")
        last = label
    audio_idx = len(images)
    chains.append(f"[{audio_idx}:a]atrim=0:{total:.3f},afade=t=out:st={max(0, total - 1):.3f}:d=1,"
                  f"aresample=48000[aout]")

    cmd += ["-filter_complex", ";".join(chains), "-map", f"[{last}]", "-map", "[aout]",
            "-t", f"{total:.3f}", "-r", str(fps),
            "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-preset", "medium",
            "-crf", "23", "-maxrate", "6M", "-bufsize", "12M", "-g", str(fps * 2),
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(out)]
    return cmd


class SlideshowVideo(VideoProvider):
    name = "slideshow"

    def pick_audio(self, seed: str) -> Path | None:
        folder = self.settings.path(self.settings.get("video.audio_dir", "audio"))
        tracks = sorted(p for p in folder.glob("*") if p.suffix.lower() in AUDIO_EXTS) if folder.is_dir() else []
        if not tracks:
            return None
        return tracks[int(hashlib.sha1(seed.encode()).hexdigest()[:6], 16) % len(tracks)]

    def generate(self, images: list[Path], out_path: Path, **opts) -> Path:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("ffmpeg no está instalado")
        fmt = self.settings.bible["formats"]["reel"]
        seed = opts.get("seed", out_path.stem)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = build_command(
            images, out_path, size=tuple(fmt["size"]), fps=fmt.get("fps", 30),
            seconds_per_image=opts.get("seconds_per_image", fmt.get("seconds_per_image", 2.5)),
            fade=self.settings.get("video.fade", 0.4), zoom=self.settings.get("video.zoom", 0.08),
            audio=opts.get("audio", self.pick_audio(seed)), seed=seed,
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg falló: {proc.stderr[-1500:]}")
        return out_path


def get_video_provider(settings) -> VideoProvider:
    name = settings.get("video.provider", "slideshow")
    if name == "slideshow":
        return SlideshowVideo(settings)
    raise ValueError(f"video.provider desconocido: {name}")
