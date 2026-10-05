import io

from PIL import Image

from mono.llm.mock import MockLLM
from mono.pipeline import ingest, load_batch, plan_batch, render_batch, render_item
from mono.providers import GenerationRequest, GenerationResult, ImageProvider
from mono.providers.image_cloudflare import CloudflareProvider
from mono.providers.image_mock import MockImageProvider


def test_cloudflare_form(settings, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    prov = CloudflareProvider(settings)
    req = GenerationRequest("x-01", "a macaque reading", "story", settings.reference_images(),
                            [settings.path("scenes", "tienda_camisetas", "tienda_01.jpg")], seed=5)
    data, files = prov.build_form(req)
    assert data["width"] == "864" and data["height"] == "1536" and data["seed"] == "5"
    assert list(files) == ["input_image_0", "input_image_1", "input_image_2", "input_image_3"]
    for _, blob, _ in files.values():
        assert max(Image.open(io.BytesIO(blob)).size) < 512
    assert data["prompt"].startswith("Image 0 is the real location")
    assert "Images 1, 2, 3 show the character" in data["prompt"]


def test_dry_run_batch_produces_independent_files(settings, repo):
    batch = render_batch(settings, plan_batch(settings, 10, dry_run=True), dry_run=True)
    finals = [repo / i["files"]["final"] for i in batch["items"]]
    assert len(finals) == 10 and all(p.exists() for p in finals)
    assert all(Image.open(p).size == (1080, 1350) for p in finals)
    assert (repo / batch["dir"] / "batch.md").exists()


class AlwaysFailLLM(MockLLM):
    def _qc(self, ctx):
        return {"score": 3, "species_ok": True, "reasons": ["no se parece"]}


def test_failed_qc_retries_then_discards(settings, repo):
    batch = plan_batch(settings, 1, dry_run=True)
    item = batch["items"][0]
    render_item(settings, item, MockImageProvider(settings), AlwaysFailLLM(settings),
                repo / batch["dir"], repo / "output" / "raw")
    assert item["status"] == "discarded"
    assert len(item["qc_attempts"]) == settings.get("image.max_attempts")


class BrokenProvider(ImageProvider):
    name = "broken"

    def generate(self, req, out_dir):
        raise RuntimeError("503")


def test_provider_errors_are_logged_not_raised(settings, repo):
    item = plan_batch(settings, 1, dry_run=True)["items"][0]
    render_item(settings, item, BrokenProvider(settings), MockLLM(settings), repo / "out", repo / "raw")
    assert item["status"] == "discarded"
    assert "503" in item["qc_attempts"][0]["error"]


def test_manual_flow_pack_then_ingest(settings, repo, monkeypatch):
    monkeypatch.setattr("mono.pipeline.get_llm", lambda s, dry_run=False: MockLLM(s))
    (repo / "inbox").mkdir()
    batch = render_batch(settings, plan_batch(settings, 2), provider_name="manual")
    assert all(i["status"] == "awaiting_manual" for i in batch["items"])
    pack = repo / batch["items"][0]["files"]["manual_pack"]
    assert "inbox/" in pack.read_text() and batch["items"][0]["prompt"][:40] in pack.read_text()

    target = batch["items"][0]["id"]
    Image.open(settings.reference_images()[0]).save(repo / "inbox" / f"{target}.png")
    done = ingest(settings)
    assert [i["id"] for i in done] == [target]
    reloaded = load_batch(repo / batch["dir"])
    assert reloaded["items"][0]["status"] == "draft"
    assert reloaded["items"][1]["status"] == "awaiting_manual"
    assert not (repo / "inbox" / f"{target}.png").exists()
    history = (repo / "data" / "history.jsonl").read_text()
    assert '"status": "draft"' in history and '"status": "awaiting_manual"' in history


def test_result_dataclass():
    assert GenerationResult(None, "manual").path is None


# --- cuota agotada ------------------------------------------------------------

class FakeResp:
    def __init__(self, status, text):
        self.status_code, self.text = status, text

    def json(self):
        return {}


def test_cloudflare_quota_raises_without_retry(settings, monkeypatch):
    from mono.providers import QuotaExhausted

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        return FakeResp(429, '{"errors":[{"message":"you have used up your daily free allocation","code":4006}]}')

    monkeypatch.setattr("mono.providers.image_cloudflare.requests.post", fake_post)
    monkeypatch.setattr("mono.providers.image_cloudflare.time.sleep", lambda s: None)
    req = GenerationRequest("x-01", "p", "feed", settings.reference_images())
    import pytest

    with pytest.raises(QuotaExhausted):
        CloudflareProvider(settings).generate(req, settings.path("output"))
    assert len(calls) == 1


class QuotaAfterOne(MockImageProvider):
    name = "quota"

    def __init__(self, settings):
        super().__init__(settings)
        self.calls = 0

    def generate(self, req, out_dir):
        from mono.providers import QuotaExhausted

        self.calls += 1
        if self.calls > 1:
            raise QuotaExhausted("4006")
        return super().generate(req, out_dir)


def test_render_batch_stops_at_quota(settings, repo, monkeypatch):
    from mono.providers import QUOTA_REASON

    provider = QuotaAfterOne(settings)
    monkeypatch.setattr("mono.pipeline.get_llm", lambda s, dry_run=False: MockLLM(s))
    monkeypatch.setattr("mono.pipeline.get_image_provider", lambda s, name=None, dry_run=False: provider)
    batch = render_batch(settings, plan_batch(settings, 3))
    assert [i["status"] for i in batch["items"]] == ["draft", "discarded", "discarded"]
    assert all(i["discard_reason"] == QUOTA_REASON for i in batch["items"][1:])
    assert provider.calls == 2 and batch["quota_exhausted"]


def test_generate_cli_exits_3_when_quota_leaves_nothing(settings, repo, monkeypatch):
    from typer.testing import CliRunner

    from mono.cli import app
    from mono.providers import QuotaExhausted

    class AlwaysQuota(MockImageProvider):
        def generate(self, req, out_dir):
            raise QuotaExhausted("4006")

    monkeypatch.setattr("mono.pipeline.get_llm", lambda s, dry_run=False: MockLLM(s))
    monkeypatch.setattr("mono.pipeline.get_image_provider",
                        lambda s, name=None, dry_run=False: AlwaysQuota(s))
    result = CliRunner().invoke(app, ["generate", "-n", "2"])
    assert result.exit_code == 3
    assert "cuota diaria gratis de Cloudflare" in result.output
