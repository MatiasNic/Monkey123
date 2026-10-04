import shutil
from pathlib import Path

import pytest

from mono.config import Settings

REPO = Path(__file__).resolve().parents[1]


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
