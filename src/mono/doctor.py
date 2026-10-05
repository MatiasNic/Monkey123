"""`mono doctor`: chequea que esté todo lo necesario y dice cómo arreglar lo que falta."""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass

import yaml

from .config import Settings
from .maintenance import token_days_left
from .store import Queue


@dataclass
class Check:
    area: str
    name: str
    ok: bool
    hint: str = ""
    required: bool = True


def _env_check(settings: Settings, area: str, keys: list[str], hint: str, required: bool = True) -> Check:
    missing = [k for k in keys if not settings.env(k)]
    return Check(area, ", ".join(keys), not missing, f"faltan {', '.join(missing)} — {hint}" if missing else "",
                 required)


def run_checks(settings: Settings, online: bool = False) -> list[Check]:
    checks: list[Check] = []
    llm = settings.get("llm.provider", "claude_cli")
    if llm == "claude_cli":
        checks.append(Check("Claude", "binario claude", bool(shutil.which("claude")),
                            "npm install -g @anthropic-ai/claude-code"))
        checks.append(_env_check(settings, "Claude", ["CLAUDE_CODE_OAUTH_TOKEN"],
                                 "corré `claude setup-token` (en local alcanza con estar logueado)", required=False))
    elif llm == "anthropic_api":
        checks.append(_env_check(settings, "Claude", ["ANTHROPIC_API_KEY"], "console.anthropic.com"))

    if settings.get("image.provider", "cloudflare") == "cloudflare":
        checks.append(_env_check(settings, "Imagen", ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"],
                                 "dash.cloudflare.com → Workers AI → API token"))
    checks.append(Check("Video", "ffmpeg", bool(shutil.which("ffmpeg")), "apt install ffmpeg / brew install ffmpeg"))

    checks.append(_env_check(settings, "Publicación", ["IG_USER_ID", "IG_ACCESS_TOKEN"],
                             "developers.facebook.com → Instagram → API setup with Instagram login"))
    checks.append(_env_check(settings, "Publicación",
                             ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET",
                              "R2_PUBLIC_BASE_URL"], "Cloudflare → R2 (ver README)"))
    checks.append(Check("Publicación", "boto3", importlib.util.find_spec("boto3") is not None,
                        'pip install -e ".[publish]"'))
    checks.append(_env_check(settings, "Token", ["GH_PAT"],
                             "token fine-grained con 'Secrets: read & write' (solo en GitHub Actions)",
                             required=False))

    if settings.get("storage.drive.enabled", True):
        checks.append(_env_check(settings, "Drive", ["DRIVE_WEBHOOK_URL", "DRIVE_WEBHOOK_SECRET"],
                                 "publicá integrations/drive_apps_script.gs (ver README)", required=False))

    channel_keys = {"email": ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "NOTIFY_EMAIL_TO"],
                    "telegram": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]}
    for channel in settings.get("notifications.channels", ["github_issue"]):
        if channel in channel_keys:
            checks.append(_env_check(settings, "Avisos", channel_keys[channel], f"canal {channel}", required=False))

    if online:
        checks += _online_checks(settings)
    return checks


def _online_checks(settings: Settings) -> list[Check]:
    out = []
    try:
        from .publish.instagram import InstagramClient

        used, total = InstagramClient.from_settings(settings).publishing_quota()
        out.append(Check("Online", f"Instagram API ({used}/{total} posts en 24 h)", True))
    except Exception as exc:  # noqa: BLE001
        out.append(Check("Online", "Instagram API", False, str(exc)[:200]))
    try:
        from .publish.media_host import R2Host

        host = R2Host(settings)
        host.client.head_bucket(Bucket=host.bucket)
        out.append(Check("Online", "bucket R2", True))
    except Exception as exc:  # noqa: BLE001
        out.append(Check("Online", "bucket R2", False, str(exc)[:200]))
    return out


def status_summary(settings: Settings) -> list[str]:
    lines = []
    days = token_days_left(settings)
    lines.append("Token IG: sin registro (corré `mono refresh-token`)" if days is None
                 else f"Token IG: vence en {days:.0f} días")
    queued = sorted((e for e in Queue(settings.path("data", "queue.yaml")).load() if e["status"] == "queued"),
                    key=lambda e: e["publish_at"])
    lines.append(f"Cola: {len(queued)} pendientes" + (f", próxima {queued[0]['publish_at']} ({queued[0]['format']})"
                                                       if queued else ""))
    pending = {"draft": 0, "awaiting_manual": 0, "qc_failed": 0}
    for batch_file in settings.path("drafts").glob("*/batch.yaml"):
        for item in (yaml.safe_load(batch_file.read_text()) or {}).get("items", []):
            if item.get("status") in pending:
                pending[item["status"]] += 1
    lines.append("Borradores: " + ", ".join(f"{k}={v}" for k, v in pending.items()))
    return lines
