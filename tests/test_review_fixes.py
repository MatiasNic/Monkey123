"""Regresiones de la revisión del PR #1 (paquetes manuales, modo auto, captions de secuencias)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from mono.cli import app
from mono.llm.mock import MockLLM
from mono.pipeline import load_batch, plan_batch, render_batch
from mono.providers.image_mock import MockImageProvider
from mono.scheduling import approve_batches

SUNDAY = datetime(2026, 10, 4, 10, 0, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))


class RecordingLLM(MockLLM):
    """Mock que registra para cuántas piezas se pidió cada caption."""

    def __init__(self, settings):
        super().__init__(settings)
        self.caption_calls = []

    def _caption(self, ctx):
        n = len(ctx["items"])
        self.caption_calls.append([i["id"] for i in ctx["items"]])
        return {"caption": f"caption de {n}", "alt_text": f"alt de {n} fotos", "hashtags": ["#x"]}


class BrokenCaptionLLM(MockLLM):
    def _caption(self, ctx):
        raise RuntimeError("sin crédito")


@pytest.fixture
def make_batch(settings, monkeypatch):
    monkeypatch.setattr("mono.pipeline.get_llm", lambda s, dry_run=False: MockLLM(s))
    monkeypatch.setattr("mono.pipeline.get_image_provider", lambda s, name=None, dry_run=False: MockImageProvider(s))
    return lambda fmt, n: render_batch(settings, plan_batch(settings, n, fmt=fmt))


def test_manual_pack_lives_in_drafts_so_the_pr_includes_it(settings, repo, monkeypatch):
    monkeypatch.setattr("mono.pipeline.get_llm", lambda s, dry_run=False: MockLLM(s))
    (repo / "inbox").mkdir()
    batch = render_batch(settings, plan_batch(settings, 2), provider_name="manual")
    for item in batch["items"]:
        pack = item["files"]["manual_pack"]
        assert pack.startswith(f"{batch['dir']}/manual/"), pack
        assert not pack.startswith("output/")
        assert (repo / pack).exists()


def test_config_command_exposes_value(settings, repo, tmp_path, monkeypatch):
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    result = CliRunner().invoke(app, ["config", "approval_mode"])
    assert result.exit_code == 0 and result.output.strip() == "approval"
    assert "value=approval" in out.read_text()
    assert CliRunner().invoke(app, ["config", "no.existe"]).exit_code != 0


def test_carousel_caption_regenerated_when_slides_removed(settings, repo, make_batch):
    batch = make_batch("carousel", 3)
    original = batch["caption"]
    assert batch["caption_items"] == [i["id"] for i in batch["items"]]
    (repo / batch["items"][1]["files"]["final"]).unlink()
    llm = RecordingLLM(settings)
    created = approve_batches(settings, now=SUNDAY, llm=llm)
    kept = [batch["items"][0]["id"], batch["items"][2]["id"]]
    assert llm.caption_calls == [kept]
    assert created[0]["caption"].startswith("caption de 2") and created[0]["alt_text"] == "alt de 2 fotos"
    reloaded = load_batch(repo / batch["dir"])
    assert reloaded["caption_items"] == kept and reloaded["caption"] != original


def test_single_surviving_slide_gets_its_own_caption(settings, repo, make_batch):
    batch = make_batch("carousel", 2)
    (repo / batch["items"][0]["files"]["final"]).unlink()
    llm = RecordingLLM(settings)
    created = approve_batches(settings, now=SUNDAY, llm=llm)
    assert created[0]["format"] == "feed"
    assert llm.caption_calls == [[batch["items"][1]["id"]]]
    assert created[0]["alt_text"] == "alt de 1 fotos"


def test_unchanged_carousel_does_not_call_llm(settings, repo, make_batch):
    make_batch("carousel", 3)
    llm = RecordingLLM(settings)
    created = approve_batches(settings, now=SUNDAY, llm=llm)
    assert llm.caption_calls == [] and created[0]["format"] == "carousel"


def test_llm_failure_keeps_text_but_drops_alt_text(settings, repo, make_batch):
    batch = make_batch("reel", 3)
    (repo / batch["items"][2]["files"]["final"]).unlink()
    created = approve_batches(settings, now=SUNDAY, llm=BrokenCaptionLLM(settings))
    assert created[0]["format"] == "reel"
    assert created[0]["caption"].startswith(batch["caption"]["caption"])
    assert created[0]["alt_text"] == ""
