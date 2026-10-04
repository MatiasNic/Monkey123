"""CLI: `mono generate | history` (más comandos en fases siguientes). Todo soporta --dry-run."""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Optional

import typer

from .config import Settings
from .store import History

app = typer.Typer(add_completion=False, help="Mono Urbano — pipeline de contenido para Instagram")

FORMATS = ("feed", "carousel", "story", "reel")


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@app.command()
def generate(
    count: int = typer.Option(4, "--count", "-n", help="Cantidad de piezas (archivos independientes)"),
    fmt: str = typer.Option("feed", "--format", "-f", help="feed | carousel | story | reel"),
    scene: Optional[str] = typer.Option(None, help="Carpeta en scenes/ a usar como lugar de referencia"),
    theme: Optional[str] = typer.Option(None, help="Tema o pista para la ideación"),
    dry_run: bool = typer.Option(False, "--dry-run", help="LLM mock, sin red y sin tocar data/"),
):
    """Genera una tanda nueva: ideas variadas + prompts de imagen."""
    from .pipeline import plan_batch

    if fmt not in FORMATS:
        raise typer.BadParameter(f"formato inválido: {fmt}")
    if fmt == "carousel" and not 2 <= count <= 10:
        raise typer.BadParameter("un carrusel lleva entre 2 y 10 imágenes")
    settings = Settings.load()
    if scene and not settings.path("scenes", scene).is_dir():
        raise typer.BadParameter(f"no existe scenes/{scene}")
    batch = plan_batch(settings, count, fmt=fmt, scene=scene, theme=theme, dry_run=dry_run)
    for item in batch["items"]:
        typer.echo(f"{item['id']}  [{item['camera_look']}] {item['concept_es'] or item['concept']}")
    typer.echo(f"\nTanda guardada en {batch['dir']}/batch.yaml")


@app.command()
def history(
    last: int = typer.Option(20, help="Cuántas piezas mostrar"),
    status: Optional[str] = typer.Option(None, help="Filtrar por estado"),
    stats: bool = typer.Option(False, help="Mostrar distribución por ejes"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Muestra el historial de piezas."""
    records = History(Settings.load().path("data", "history.jsonl")).all()
    if status:
        records = [r for r in records if r.get("status") == status]
    if stats:
        for axis in ("status", "format", "location", "camera_look", "pose", "lighting"):
            typer.echo(f"{axis}: {dict(Counter(str(r.get(axis)) for r in records).most_common(8))}")
        return
    records = records[-last:]
    if as_json:
        typer.echo(json.dumps(records, ensure_ascii=False, indent=2))
        return
    for r in records:
        typer.echo(f"{r['id']}  {r['status']:<10} {r['format']:<8} {r.get('location')} — {r.get('activity')}")


if __name__ == "__main__":
    app()
