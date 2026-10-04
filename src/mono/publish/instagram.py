"""Cliente mínimo de la Instagram API con Instagram Login (Content Publishing).

Flujo: POST /{ig-user-id}/media → contenedor; GET /{container}?fields=status_code hasta FINISHED;
POST /{ig-user-id}/media_publish (creation_id). Límite: 100 publicaciones por API cada 24 h.
Etiqueta de IA: `is_ai_generated=true` (no disponible en hijos de carrusel).
Docs: https://developers.facebook.com/docs/instagram-platform/content-publishing/
"""

from __future__ import annotations

import logging
import time

import requests

from ..config import Settings

log = logging.getLogger(__name__)
HOST = "https://graph.instagram.com"


class InstagramError(RuntimeError):
    pass


# --- payloads (funciones puras, testeables sin red) -------------------------

def _bool(value: bool) -> str:
    return "true" if value else "false"


def build_image_payload(image_url: str, caption: str = "", alt_text: str = "", ai: bool = True) -> dict:
    payload = {"image_url": image_url}
    if caption:
        payload["caption"] = caption
    if alt_text:
        payload["alt_text"] = alt_text[:1000]
    if ai:
        payload["is_ai_generated"] = _bool(True)
    return payload


def build_story_payload(image_url: str, ai: bool = True) -> dict:
    # Las historias no aceptan caption ni alt_text.
    payload = {"image_url": image_url, "media_type": "STORIES"}
    if ai:
        payload["is_ai_generated"] = _bool(True)
    return payload


def build_carousel_item_payload(image_url: str, alt_text: str = "") -> dict:
    # Sin caption ni is_ai_generated: no están soportados en hijos de carrusel.
    payload = {"image_url": image_url, "is_carousel_item": _bool(True)}
    if alt_text:
        payload["alt_text"] = alt_text[:1000]
    return payload


def build_carousel_payload(children: list[str], caption: str = "", ai: bool = True) -> dict:
    if not 2 <= len(children) <= 10:
        raise ValueError("un carrusel lleva entre 2 y 10 elementos")
    payload = {"media_type": "CAROUSEL", "children": ",".join(children)}
    if caption:
        payload["caption"] = caption
    if ai:
        payload["is_ai_generated"] = _bool(True)
    return payload


# --- cliente ----------------------------------------------------------------

class InstagramClient:
    def __init__(self, user_id: str, token: str, api_version: str = "v25.0", http=requests,
                 poll_seconds: float = 3, poll_timeout: float = 300, sleep=time.sleep):
        self.user_id, self.token, self.version = user_id, token, api_version
        self.http, self.poll_seconds, self.poll_timeout, self.sleep = http, poll_seconds, poll_timeout, sleep

    @classmethod
    def from_settings(cls, settings: Settings) -> "InstagramClient":
        return cls(
            settings.env("IG_USER_ID", required=True),
            settings.env("IG_ACCESS_TOKEN", required=True),
            api_version=settings.get("instagram.api_version", "v25.0"),
            poll_seconds=settings.get("instagram.poll_seconds", 3),
            poll_timeout=settings.get("instagram.poll_timeout", 300),
        )

    def _url(self, path: str) -> str:
        return f"{HOST}/{self.version}/{path.lstrip('/')}"

    def _check(self, resp) -> dict:
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            raise InstagramError(f"HTTP {resp.status_code}: {err.get('message') or resp.text[:300]}")
        return data

    def _post(self, path: str, payload: dict) -> dict:
        return self._check(self.http.post(self._url(path), data={**payload, "access_token": self.token}, timeout=60))

    def _get(self, path: str, params: dict | None = None) -> dict:
        return self._check(self.http.get(self._url(path), params={**(params or {}), "access_token": self.token},
                                         timeout=60))

    def create_container(self, payload: dict) -> str:
        return self._post(f"{self.user_id}/media", payload)["id"]

    def wait_ready(self, container_id: str) -> None:
        waited = 0.0
        while True:
            status = self._get(container_id, {"fields": "status_code,status"}).get("status_code")
            if status in ("FINISHED", "PUBLISHED"):
                return
            if status in ("ERROR", "EXPIRED"):
                raise InstagramError(f"contenedor {container_id} en estado {status}")
            if waited >= self.poll_timeout:
                raise InstagramError(f"timeout esperando el contenedor {container_id} (último estado: {status})")
            self.sleep(self.poll_seconds)
            waited += self.poll_seconds

    def publish(self, container_id: str) -> str:
        return self._post(f"{self.user_id}/media_publish", {"creation_id": container_id})["id"]

    def permalink(self, media_id: str) -> str:
        try:
            return self._get(media_id, {"fields": "permalink"}).get("permalink", "")
        except InstagramError:
            return ""

    def publishing_quota(self) -> tuple[int, int]:
        """(usadas, total) en las últimas 24 h."""
        data = self._get(f"{self.user_id}/content_publishing_limit", {"fields": "quota_usage,config"})
        row = (data.get("data") or [{}])[0]
        return int(row.get("quota_usage", 0)), int((row.get("config") or {}).get("quota_total", 100))

    def refresh_token(self) -> dict:
        resp = self.http.get(f"{HOST}/refresh_access_token",
                             params={"grant_type": "ig_refresh_token", "access_token": self.token}, timeout=60)
        return self._check(resp)


class DryRunInstagram(InstagramClient):
    """Registra las llamadas y devuelve ids ficticios."""

    def __init__(self, *args, **kwargs):
        super().__init__("DRY_USER", "DRY_TOKEN")
        self.calls: list[tuple[str, dict]] = []
        self._n = 0

    def _fake_id(self) -> str:
        self._n += 1
        return f"dry-{self._n}"

    def create_container(self, payload):
        self.calls.append(("POST /media", payload))
        return self._fake_id()

    def wait_ready(self, container_id):
        self.calls.append(("GET status_code", {"id": container_id}))

    def publish(self, container_id):
        self.calls.append(("POST /media_publish", {"creation_id": container_id}))
        return self._fake_id()

    def permalink(self, media_id):
        return f"https://www.instagram.com/p/{media_id}/"

    def publishing_quota(self):
        return 0, 100

    def refresh_token(self):
        return {"access_token": "DRY_TOKEN_REFRESHED", "expires_in": 5184000}
