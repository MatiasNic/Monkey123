import shutil
from pathlib import Path

import pytest

from mono.config import Settings

REPO = Path(__file__).resolve().parents[1]


# Credenciales que los tests nunca deben usar de verdad (el entorno de quien corre los tests puede tenerlas).
SENSITIVE_ENV = (
    "GITHUB_TOKEN", "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_SERVER_URL", "GITHUB_OUTPUT", "GITHUB_ACTIONS",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "NOTIFY_EMAIL_TO",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "IG_USER_ID", "IG_ACCESS_TOKEN", "GH_PAT", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
    "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_BASE_URL",
    "ANTHROPIC_API_KEY", "DRIVE_WEBHOOK_URL", "DRIVE_WEBHOOK_SECRET",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    for key in SENSITIVE_ENV:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Copia mínima del repo en tmp para que los tests no toquen data/ real."""
    for name in ("config.yaml", "character", "prompts", "scenes"):
        src = REPO / name
        (shutil.copytree if src.is_dir() else shutil.copy)(src, tmp_path / name)
    (tmp_path / "data").mkdir()
    shutil.copy(REPO / "data" / "idea_bank.yaml", tmp_path / "data")
    (tmp_path / "data" / "history.jsonl").write_text("")
    monkeypatch.setenv("MONO_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def settings(repo):
    return Settings.load(repo)
