import base64
import pytest
from typer.testing import CliRunner

from mono.cli import app
from mono.llm.mock import MockLLM
from mono.pipeline import plan_batch, render_batch
from mono.prompting.builder import build_image_prompt
from mono.providers.image_mock import MockImageProvider
from mono.qc.vision_qc import evaluate
from mono.storage.drive import DriveUploader, batch_folder, sync_batch, sync_published


class Resp:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class FakeHTTP:
    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    def post(self, url, json=None, timeout=None):
        self.calls.append(json)
        return Resp({"ok": True, "url": f"https://drive/{json['filename']}"} if self.ok
                    else {"ok": False, "error": "secret inválido"})


@pytest.fixture
def batch(settings, repo, monkeypatch):
    monkeypatch.setattr("mono.pipeline.get_llm", lambda s, dry_run=False: MockLLM(s))
    monkeypatch.setattr("mono.pipeline.get_image_provider", lambda s, name=None, dry_run=False: MockImageProvider(s))
    b = render_batch(settings, plan_batch(settings, 2))
    rejected = repo / "output" / "rejected" / b["id"]
    rejected.mkdir(parents=True)
    (rejected / f"{b['items'][0]['id']}_a1.png").write_bytes(b"x")
    return b


def test_batch_folder_name():
    assert batch_folder("20261004-2213-c25d") == "tandas/2026-10-04_20261004-2213-c25d"


def test_sync_batch_uploads_approved_rejected_and_summary(settings, repo, batch):
    http = FakeHTTP()
    up = DriveUploader("https://script", "s3cret", http=http)
    sync_batch(settings, up, repo / batch["dir"])
    base = batch_folder(batch["id"])
    paths = {(c["path"], c["filename"]) for c in http.calls}
    assert (f"{base}/aprobadas", f"{batch['items'][0]['id']}.jpg") in paths
    assert (f"{base}/descartadas", f"{batch['items'][0]['id']}_a1.png") in paths
    assert (base, "resumen.md") in paths
    call = http.calls[0]
    assert call["secret"] == "s3cret" and base64.b64decode(call["base64"])


def test_bad_secret_raises_without_retrying_forever(settings, repo, batch, monkeypatch):
    monkeypatch.setattr("mono.storage.drive.time.sleep", lambda s: None)
    http = FakeHTTP(ok=False)
    up = DriveUploader("https://script", "mal", http=http)
    with pytest.raises(RuntimeError, match="secret"):
        up.upload(repo / batch["items"][0]["files"]["final"], "x")
    assert len(http.calls) == 1


def test_sync_published_writes_caption_txt(settings, repo, batch):
    http = FakeHTTP()
    up = DriveUploader("https://script", "s", http=http)
    entry = {"id": "post-1", "format": "feed", "files": [batch["items"][0]["files"]["final"]],
             "caption": "otro martes.", "permalink": "https://instagram.com/p/x", "published_at": "2026-10-06T22:07:00"}
    sync_published(settings, up, entry)
    names = [(c["path"], c["filename"]) for c in http.calls]
    assert names == [("publicadas/2026-10", "post-1_01.jpg"), ("publicadas/2026-10", "post-1.txt")]
    assert "otro martes." in base64.b64decode(http.calls[1]["base64"]).decode()


def test_unconfigured_drive_is_skipped(settings, repo):
    assert DriveUploader.from_settings(settings) is None
    result = CliRunner().invoke(app, ["drive-sync"])
    assert result.exit_code == 0 and "no configurado" in result.output


def test_drive_sync_dry_run_lists_paths(settings, repo, batch):
    result = CliRunner().invoke(app, ["drive-sync", "--batch", batch["id"], "--dry-run"])
    assert result.exit_code == 0, result.output
    assert f"[dry-run] Monkey/{batch_folder(batch['id'])}/aprobadas/" in result.output


def test_publish_copy_to_drive_never_breaks(settings, repo, monkeypatch):
    from mono.publish.publisher import _copy_to_drive

    monkeypatch.setenv("DRIVE_WEBHOOK_URL", "https://script")
    monkeypatch.setenv("DRIVE_WEBHOOK_SECRET", "s")

    def boom(*a, **k):
        raise RuntimeError("drive caído")
    monkeypatch.setattr("mono.storage.drive.sync_published", boom)
    _copy_to_drive(settings, [{"id": "p", "status": "published", "files": []}])  # no lanza


# --- anatomía ---------------------------------------------------------------

class ExtraFootLLM(MockLLM):
    def _qc(self, ctx):
        return {"score": 9, "species_ok": True, "anatomy": 8, "limb_count_ok": False,
                "anatomy_issues": ["3 pies visibles"], "reasons": ["linda foto"]}


class LowAnatomyLLM(MockLLM):
    def _qc(self, ctx):
        return {"score": 8, "species_ok": True, "anatomy": 4, "limb_count_ok": True, "reasons": []}


def test_extra_limbs_are_a_hard_fail(settings):
    ref = settings.reference_images()[0]
    result = evaluate(settings, ExtraFootLLM(settings), ref, {"description": "x"})
    assert not result.passed and "3 pies" in result.reasons[0]
    assert not evaluate(settings, LowAnatomyLLM(settings), ref, {"description": "x"}).passed
    assert evaluate(settings, MockLLM(settings), ref, {"description": "x"}).passed


def test_image_prompt_demands_correct_anatomy(settings):
    from mono.ideation.ideas import generate_ideas

    idea = generate_ideas(settings, MockLLM(settings), 1, update_bank=False)[0]
    prompt = build_image_prompt(settings, idea)["prompt"]
    assert "exactly two arms, two hands, two legs and two feet" in prompt
    assert "extra feet" in prompt
