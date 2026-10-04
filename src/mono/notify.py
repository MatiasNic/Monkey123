"""Avisos gratis y configurables: GitHub Issues (dedup), email (SMTP) y Telegram.

config.yaml → notifications.channels / notifications.events. Un canal sin credenciales se saltea con un
warning: un aviso nunca rompe el flujo principal.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

import requests

from .config import Settings

log = logging.getLogger(__name__)
EVENTS = ("failure", "published", "batch_ready", "token_refreshed", "token_expiring")
ALERT_LABEL = "alerta"
GITHUB_API = "https://api.github.com"


def _github_issue(settings: Settings, event: str, title: str, body: str, http=requests) -> str:
    token, repo = os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        raise LookupError("faltan GITHUB_TOKEN / GITHUB_REPOSITORY")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    resp = http.get(f"{GITHUB_API}/repos/{repo}/issues", headers=headers,
                    params={"state": "open", "labels": ALERT_LABEL, "per_page": 100}, timeout=30)
    resp.raise_for_status()
    for issue in resp.json():
        if issue.get("title") == title and "pull_request" not in issue:
            http.post(f"{GITHUB_API}/repos/{repo}/issues/{issue['number']}/comments", headers=headers,
                      json={"body": body}, timeout=30).raise_for_status()
            return f"comentado en #{issue['number']}"
    created = http.post(f"{GITHUB_API}/repos/{repo}/issues", headers=headers,
                        json={"title": title, "body": body, "labels": [ALERT_LABEL, event]}, timeout=30)
    created.raise_for_status()
    return f"issue #{created.json().get('number')}"


def _email(settings: Settings, event: str, title: str, body: str, smtp_cls=smtplib.SMTP) -> str:
    host, to = settings.env("SMTP_HOST"), settings.env("NOTIFY_EMAIL_TO")
    user, password = settings.env("SMTP_USER"), settings.env("SMTP_PASSWORD")
    if not (host and to and user and password):
        raise LookupError("faltan SMTP_HOST / SMTP_USER / SMTP_PASSWORD / NOTIFY_EMAIL_TO")
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = f"[mono] {title}", user, to
    msg.set_content(body)
    with smtp_cls(host, int(settings.env("SMTP_PORT") or 587), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    return f"email a {to}"


def _telegram(settings: Settings, event: str, title: str, body: str, http=requests) -> str:
    token, chat = settings.env("TELEGRAM_BOT_TOKEN"), settings.env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise LookupError("faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
    resp = http.post(f"https://api.telegram.org/bot{token}/sendMessage",
                     json={"chat_id": chat, "text": f"{title}\n\n{body}"[:4000], "disable_web_page_preview": True},
                     timeout=30)
    resp.raise_for_status()
    return f"telegram {chat}"


CHANNELS = {"github_issue": _github_issue, "email": _email, "telegram": _telegram}


def run_link() -> str:
    server, repo, run = (os.environ.get(k, "") for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run}" if server and repo and run else ""


def notify(settings: Settings, event: str, title: str, body: str = "", dry_run: bool = False,
           channels: dict | None = None) -> dict[str, str]:
    """Manda el aviso a los canales configurados. Devuelve {canal: resultado}."""
    if event not in EVENTS:
        raise ValueError(f"evento desconocido: {event} (opciones: {', '.join(EVENTS)})")
    enabled_events = settings.get("notifications.events", ["failure", "token_expiring"])
    if event not in enabled_events:
        return {}
    if link := run_link():
        body = f"{body}\n\nRun: {link}".strip()
    results = {}
    for name in settings.get("notifications.channels", ["github_issue"]):
        sender = (channels or CHANNELS).get(name)
        if sender is None:
            results[name] = "canal desconocido"
            continue
        if dry_run:
            results[name] = "dry-run"
            log.info("[dry-run] %s ← %s: %s\n%s", name, event, title, body)
            continue
        try:
            results[name] = sender(settings, event, title, body)
        except LookupError as exc:
            results[name] = f"salteado ({exc})"
            log.warning("aviso %s salteado: %s", name, exc)
        except Exception as exc:  # noqa: BLE001 — un aviso nunca rompe el flujo
            results[name] = f"error ({exc})"
            log.warning("aviso %s falló: %s", name, exc)
    return results
