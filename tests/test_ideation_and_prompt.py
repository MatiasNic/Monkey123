import json

from mono.ideation.ideas import generate_ideas
from mono.llm.mock import MockLLM
from mono.pipeline import plan_batch
from mono.prompting.builder import build_image_prompt


def test_generate_ideas_returns_distinct_ideas(settings):
    ideas = generate_ideas(settings, MockLLM(settings), 6, update_bank=False)
    assert len(ideas) == 6
    assert len({i["activity"] for i in ideas}) == 6
    assert all(i["camera_look"] in settings.bible["camera_looks"] for i in ideas)


def test_prompt_contains_identity_look_and_references(settings):
    idea = generate_ideas(settings, MockLLM(settings), 1, update_bank=False)[0]
    built = build_image_prompt(settings, idea)
    assert "macaque" in built["prompt"]
    assert settings.bible["camera_looks"][idea["camera_look"]]["prompt"] in built["prompt"]
    assert "never a baby, chimpanzee" in built["prompt"]
    assert len(built["references"]) == 4
    assert all("style_refs" not in r for r in built["references"])
    assert built["size"] == [1080, 1350]


def test_scene_photos_attached(settings):
    idea = generate_ideas(settings, MockLLM(settings), 1, scene="tienda_camisetas", update_bank=False)[0]
    built = build_image_prompt(settings, idea)
    assert built["scene_photos"] == ["scenes/tienda_camisetas/tienda_01.jpg"]
    assert "framed vintage national-team jerseys" in built["prompt"]


def test_dry_run_does_not_touch_data(settings, repo):
    before = (repo / "data" / "idea_bank.yaml").read_text()
    batch = plan_batch(settings, 10, dry_run=True)
    assert len(batch["items"]) == 10
    assert len({i["id"] for i in batch["items"]}) == 10
    assert (repo / "data" / "history.jsonl").read_text() == ""
    assert (repo / "data" / "idea_bank.yaml").read_text() == before


def test_real_run_records_history(settings, repo, monkeypatch):
    monkeypatch.setattr("mono.pipeline.get_llm", lambda s, dry_run=False: MockLLM(s))
    plan_batch(settings, 3)
    lines = (repo / "data" / "history.jsonl").read_text().splitlines()
    assert len(lines) == 3
    rec = json.loads(lines[0])
    for key in ("id", "format", "location", "activity", "pose", "camera_distance", "expression", "gaze",
                "outfit", "lighting", "accessories", "camera_look", "prompt", "status"):
        assert key in rec
    assert rec["status"] == "draft"
