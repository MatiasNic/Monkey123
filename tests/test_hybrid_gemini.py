"""Modo híbrido con Gemini: paquete con referencias, bloque del PR, inbox sin renombrar y recorte del logo."""

from PIL import Image

from mono.llm.mock import MockLLM
from mono.pipeline import ingest, load_batch, plan_batch, render_batch, review_markdown
from mono.postprocess.looks import trim_edges
from mono.providers.image_manual import find_in_inbox

BASE = "https://raw.githubusercontent.com/MatiasNic/Monkey123/generate/123"


def _manual_batch(settings, monkeypatch, n=2):
    monkeypatch.setattr("mono.pipeline.get_llm", lambda s, dry_run=False: MockLLM(s))
    return render_batch(settings, plan_batch(settings, n), provider_name="manual")


def test_pack_uses_full_references_and_the_face_prompt(settings, repo, monkeypatch):
    batch = _manual_batch(settings, monkeypatch, 1)
    item = batch["items"][0]
    refs = item["files"]["manual_refs"]
    assert refs and all(r.startswith("character/reference/") for r in refs)
    pack = (repo / item["files"]["manual_pack"]).read_text()
    assert "Gemini" in pack and "heavy half-closed eyelids" in pack and item["prompt"] in pack
    assert "$" not in pack.replace("$ ", "")


def test_pr_body_has_prompt_reference_links_and_upload_link(settings, repo, monkeypatch):
    batch = _manual_batch(settings, monkeypatch, 1)
    md = review_markdown(batch, BASE)
    assert "https://github.com/MatiasNic/Monkey123/upload/generate/123/inbox" in md
    assert f"{BASE}/character/reference/" in md
    assert "```text" in md and "01.jpg" in md


def test_inbox_accepts_short_names(tmp_path):
    (tmp_path / "2.png").write_bytes(b"x")
    (tmp_path / "foto-03.jpg").write_bytes(b"x")
    assert find_in_inbox(tmp_path, "20261010-0133-ba73-02") is None
    assert find_in_inbox(tmp_path, "20261010-0133-ba73-02", allow_short=True).name == "2.png"
    assert find_in_inbox(tmp_path, "20261010-0133-ba73-03", allow_short=True).name == "foto-03.jpg"
    assert find_in_inbox(tmp_path, "20261010-0133-ba73-12", allow_short=True) is None


def test_ingest_takes_short_name_and_trims_logo(settings, repo, monkeypatch):
    batch = _manual_batch(settings, monkeypatch, 2)
    (repo / "inbox").mkdir(exist_ok=True)
    Image.open(settings.reference_images()[0]).convert("RGB").save(repo / "inbox" / "01.jpg")
    done = ingest(settings)
    assert [i["id"] for i in done] == [batch["items"][0]["id"]]
    reloaded = load_batch(repo / batch["dir"])
    assert reloaded["items"][0]["status"] == "draft"
    assert reloaded["items"][1]["status"] == "awaiting_manual"


def test_trim_edges_cuts_each_border():
    img = Image.new("RGB", (1000, 1250))
    assert trim_edges(img, 0.04).size == (920, 1150)
    assert trim_edges(img, 0).size == (1000, 1250)
