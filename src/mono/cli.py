"""CLI: `mono generate | history` (más comandos en fases siguientes). Todo soporta --dry-run."""

from __future__ import annotations

import json
import logging
import os
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
    provider: Optional[str] = typer.Option(None, help="cloudflare | manual | mock (default: config.yaml)"),
    ideas_only: bool = typer.Option(False, "--ideas-only", help="Solo ideas + prompts, sin generar imágenes"),
    dry_run: bool = typer.Option(False, "--dry-run", help="LLM e imagen mock, sin red y sin tocar data/"),
):
    """Genera una tanda nueva: ideas → prompts → imágenes → QC → post-proceso."""
    from .pipeline import plan_batch, render_batch

    if fmt not in FORMATS:
        raise typer.BadParameter(f"formato inválido: {fmt}")
    if fmt in ("carousel", "reel") and not 2 <= count <= 10:
        raise typer.BadParameter("un carrusel o reel lleva entre 2 y 10 imágenes")
    settings = Settings.load()
    if scene and not settings.path("scenes", scene).is_dir():
        raise typer.BadParameter(f"no existe scenes/{scene}")
    batch = plan_batch(settings, count, fmt=fmt, scene=scene, theme=theme, dry_run=dry_run)
    if not ideas_only:
        batch = render_batch(settings, batch, provider_name=provider, dry_run=dry_run)
    _github_output(batch_id=batch["id"], batch_dir=batch["dir"], count=len(batch["items"]))
    if settings.get("approval_mode") == "auto" and not dry_run and not ideas_only:
        from .scheduling import approve_batches

        approve_batches(settings, [settings.path(batch["dir"])])
    for item in batch["items"]:
        typer.echo(f"{item['id']}  {item['status']:<16} [{item['camera_look']}] {item['concept_es'] or item['concept']}")
    typer.echo(f"\nTanda guardada en {batch['dir']}/ (batch.yaml + batch.md)")


@app.command()
def ingest(
    batch: Optional[str] = typer.Option(None, help="Id de tanda (default: todas las de drafts/)"),
    force: bool = typer.Option(False, help="Aceptar aunque no pase el QC"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Procesa imágenes generadas a mano y subidas a inbox/<id>.jpg (QC → post-proceso)."""
    from .pipeline import ingest as run_ingest

    settings = Settings.load()
    dirs = [settings.path("drafts", batch)] if batch else None
    items = run_ingest(settings, dirs, force=force, dry_run=dry_run)
    if not items:
        typer.echo("No hay imágenes nuevas en inbox/ para piezas pendientes.")
    for item in items:
        typer.echo(f"{item['id']}  {item['status']}  QC {item['qc']['score']:.1f}")


def _github_output(**values) -> None:
    """Expone valores a los pasos siguientes de GitHub Actions."""
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a") as fh:
            for key, value in values.items():
                fh.write(f"{key}={value}\n")


@app.command()
def review(
    batch: str = typer.Argument(..., help="Id de tanda"),
    image_base: str = typer.Option("", help="URL base para las imágenes (cuerpo del PR)"),
):
    """Imprime el resumen markdown de una tanda (lo usa el workflow para el cuerpo del PR)."""
    from .pipeline import load_batch, review_markdown

    settings = Settings.load()
    folder = settings.path("drafts", batch)
    if not folder.exists():
        folder = settings.path("output", "dry-run", batch)
    typer.echo(review_markdown(load_batch(folder), image_base))


@app.command()
def approve(
    batch: Optional[str] = typer.Option(None, help="Id de tanda (default: todas las de drafts/)"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Aprueba las piezas en borrador de tandas mergeadas y las agenda en data/queue.yaml."""
    from .scheduling import approve_batches

    settings = Settings.load()
    dirs = [settings.path("drafts", batch)] if batch else None
    created = approve_batches(settings, dirs, dry_run=dry_run)
    if not created:
        typer.echo("Nada nuevo para encolar.")
    for entry in created:
        typer.echo(f"{entry['publish_at']}  {entry['format']:<8} {entry['id']}  ({len(entry['files'])} img)")


@app.command()
def queue(
    due: bool = typer.Option(False, help="Solo lo que ya corresponde publicar"),
    count: bool = typer.Option(False, "--count", help="Imprimir solo la cantidad (y exponerla a Actions)"),
):
    """Muestra la cola de publicación."""
    from .scheduling import due_posts
    from .store import Queue

    settings = Settings.load()
    entries = due_posts(settings) if due else Queue(settings.path("data", "queue.yaml")).load()
    if count:
        typer.echo(len(entries))
        _github_output(count=len(entries))
        return
    for e in entries:
        typer.echo(f"{e['publish_at']}  {e['status']:<10} {e['format']:<8} {e['id']}  {e['caption'][:50]!r}")


@app.command()
def publish(
    post_id: Optional[str] = typer.Option(None, "--id", help="Publicar esta entrada aunque no esté vencida"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra las llamadas a la API sin ejecutarlas"),
):
    """Publica en Instagram lo que vence en data/queue.yaml."""
    from .publish.publisher import publish_due

    done = publish_due(Settings.load(), dry_run=dry_run, only_id=post_id)
    if not done:
        typer.echo("Nada para publicar ahora.")
    failed = False
    for e in done:
        typer.echo(f"{e['status']:<10} {e['format']:<8} {e['id']}  {e.get('permalink') or e.get('last_error') or ''}")
        failed |= e["status"] != "published"
    if failed:
        raise typer.Exit(1)


@app.command("publish-test")
def publish_test(
    image: str = typer.Argument(..., help="Imagen a publicar (cualquier formato)"),
    caption: str = typer.Option("prueba.", help="Caption del post"),
    story: bool = typer.Option(False, "--story", help="Publicar como historia"),
    look: str = typer.Option("35mm_kodak_portra", help="Look de post-proceso a aplicar"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Primer post de prueba: procesa una imagen y la publica directo (sin cola)."""
    from pathlib import Path

    from .postprocess.looks import process
    from .publish.instagram import DryRunInstagram, InstagramClient
    from .publish.media_host import get_media_host
    from .publish.publisher import publish_entry

    settings = Settings.load()
    fmt = "story" if story else "feed"
    size = tuple(settings.bible["formats"][fmt]["size"])
    out = settings.path("output", "publish-test", f"test-{Path(image).stem}.jpg")
    process(Path(image), out, size, settings.bible["camera_looks"][look]["post"])
    entry = {"id": f"test-{Path(image).stem}", "format": fmt, "files": [str(out.relative_to(settings.root))],
             "caption": caption, "alt_text": ""}
    client = DryRunInstagram() if dry_run else InstagramClient.from_settings(settings)
    result = publish_entry(settings, entry, client, get_media_host(settings, dry_run=dry_run))
    for name, payload in getattr(client, "calls", []):
        typer.echo(f"[dry-run] {name} {payload}")
    typer.echo(f"Publicado: {result['permalink'] or result['media_id']}")


@app.command("refresh-token")
def refresh_token(
    write_to: Optional[str] = typer.Option(None, help="Guardar el token nuevo en este archivo (permisos 600)"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Renueva el token de larga duración de Instagram (60 días) y registra su vencimiento."""
    from pathlib import Path

    from .maintenance import record_token_refresh
    from .notify import notify
    from .publish.instagram import DryRunInstagram, InstagramClient

    settings = Settings.load()
    client = DryRunInstagram() if dry_run else InstagramClient.from_settings(settings)
    data = client.refresh_token()
    token = data["access_token"]
    if os.environ.get("GITHUB_ACTIONS"):
        typer.echo(f"::add-mask::{token}")
    if write_to:
        path = Path(write_to)
        path.touch(mode=0o600, exist_ok=True)
        path.chmod(0o600)
        path.write_text(token)
    days = int(data.get("expires_in", 0)) // 86400
    if not dry_run:
        record_token_refresh(settings, int(data.get("expires_in", 0)))
        notify(settings, "token_refreshed", "Token de Instagram renovado", f"Vence en {days} días.")
    typer.echo(f"Token renovado ({token[:4]}…{token[-4:]}), vence en {days} días.")


@app.command()
def notify(
    event: str = typer.Option(..., help="failure | published | batch_ready | token_refreshed | token_expiring"),
    title: str = typer.Option(..., help="Título del aviso"),
    body: str = typer.Option("", help="Texto del aviso"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Manda un aviso por los canales configurados (GitHub Issue, email, Telegram)."""
    from .notify import notify as send

    for channel, result in send(Settings.load(), event, title, body, dry_run=dry_run).items():
        typer.echo(f"{channel}: {result}")


@app.command()
def doctor(online: bool = typer.Option(False, help="Probar también las APIs (Instagram, R2)")):
    """Chequea configuración, credenciales y estado general."""
    from .doctor import run_checks, status_summary

    settings = Settings.load()
    checks = run_checks(settings, online=online)
    for c in checks:
        mark = "✅" if c.ok else ("❌" if c.required else "⚠️ ")
        typer.echo(f"{mark} [{c.area}] {c.name}" + (f"  → {c.hint}" if c.hint and not c.ok else ""))
    typer.echo("")
    for line in status_summary(settings):
        typer.echo(line)
    if any(not c.ok and c.required for c in checks):
        raise typer.Exit(1)


@app.command()
def prune(
    days: int = typer.Option(60, help="Antigüedad mínima de la tanda"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Borra JPG/MP4 de tandas ya publicadas o descartadas (se conserva el historial)."""
    from .maintenance import prune_media

    settings = Settings.load()
    removed = prune_media(settings, days=days, dry_run=dry_run)
    for path in removed:
        typer.echo(("[dry-run] " if dry_run else "") + str(path.relative_to(settings.root)))
    typer.echo(f"{len(removed)} archivo(s)")


@app.command("token-check")
def token_check(warn_days: int = typer.Option(10, help="Avisar si quedan menos días")):
    """Avisa (token_expiring) si el token de Instagram está por vencer o no hay registro."""
    from .maintenance import token_days_left
    from .notify import notify as send

    settings = Settings.load()
    days = token_days_left(settings)
    if days is None or days < warn_days:
        msg = ("No hay registro de vencimiento del token." if days is None
               else f"El token de Instagram vence en {days:.0f} días.")
        send(settings, "token_expiring", "Token de Instagram por vencer", msg +
             " Corré token-refresh.yml (requiere el secret GH_PAT) o generá uno nuevo en Meta.")
        typer.echo(msg)
        raise typer.Exit(1)
    typer.echo(f"Token OK: vence en {days:.0f} días.")


@app.command("plan")
def plan_cmd(
    fmt: Optional[str] = typer.Option(None, "--format", help="Forzar formato (dispatch manual)"),
    count: int = typer.Option(4, "--count"),
):
    """JSON con las tandas a generar hoy (matrix del workflow generate.yml)."""
    from .scheduling import plan_for_today

    plan = [{"format": fmt, "count": count}] if fmt else plan_for_today(Settings.load())
    typer.echo(json.dumps(plan))
    _github_output(plan=json.dumps(plan), has_work=str(bool(plan)).lower())


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
