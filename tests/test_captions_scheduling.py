from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

from mono.captions.writer import clean_hashtags, full_text
from mono.llm.mock import MockLLM
from mono.pipeline import load_batch, plan_batch, render_batch
from mono.scheduling import approve_batches, due_posts, next_slot, plan_for_today

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
SUNDAY = datetime(2026, 10, 4, 10, 0, tzinfo=TZ)


def _real_batch(settings, monkeypatch, n, fmt):
    monkeypatch.setattr("mono.pipeline.get_llm", lambda s, dry_run=False: MockLLM(s))
    monkeypatch.setattr("mono.pipeline.get_image_provider",
                        lambda s, name=None, dry_run=False: __import__("mono.providers.image_mock", fromlist=["x"]).MockImageProvider(s))
    return render_batch(settings, plan_batch(settings, n, fmt=fmt))


def test_clean_hashtags():
    assert clean_hashtags(["BuenosAires", "#35mm", "#35mm", "street photo"], 5) == ["#buenosaires", "#35mm", "#streetphoto"]


def test_full_text_adds_hashtags_and_disclosure(settings):
    settings.data["captions"]["ai_disclosure_text"] = "Imagen generada con IA."
    text = full_text(settings, {"caption": "otro martes.", "hashtags": ["#a", "#b"]})
    assert text == "otro martes.\n\n#a #b\n\nImagen generada con IA."


def test_feed_items_get_captions_and_stories_dont(settings, monkeypatch):
    feed = _real_batch(settings, monkeypatch, 2, "feed")
    assert all(i["caption"]["caption"] for i in feed["items"])
    story = _real_batch(settings, monkeypatch, 2, "story")
    assert all(i["caption"] is None for i in story["items"])


def test_carousel_shares_one_caption(settings, monkeypatch):
    batch = _real_batch(settings, monkeypatch, 4, "carousel")
    assert batch["caption"]
    assert all(i["caption"] == batch["caption"] for i in batch["items"])


def test_next_slot_respects_weekdays_and_taken(settings):
    first = next_slot(settings, "feed", set(), SUNDAY)
    assert first.weekday() == 0 and first.hour == 19            # lunes 19:00
    second = next_slot(settings, "feed", {("feed", first.date())}, SUNDAY)
    assert second.weekday() == 2                                 # miércoles
    assert next_slot(settings, "carousel", set(), SUNDAY).weekday() == 5
    assert next_slot(settings, "story", set(), SUNDAY).hour == 13


def test_approve_enqueues_and_respects_deleted_files(settings, repo, monkeypatch):
    feed = _real_batch(settings, monkeypatch, 3, "feed")
    carousel = _real_batch(settings, monkeypatch, 3, "carousel")
    # el revisor borró la segunda pieza del feed en el PR
    (repo / feed["items"][1]["files"]["final"]).unlink()
    created = approve_batches(settings, now=SUNDAY)
    formats = sorted(e["format"] for e in created)
    assert formats == ["carousel", "feed", "feed"]
    car = next(e for e in created if e["format"] == "carousel")
    assert len(car["files"]) == 3 and car["caption"]
    feeds = sorted(e["publish_at"] for e in created if e["format"] == "feed")
    assert [datetime.fromisoformat(d).weekday() for d in feeds] == [0, 2]
    reloaded = load_batch(repo / feed["dir"])
    assert [i["status"] for i in reloaded["items"]] == ["queued", "discarded", "queued"]
    queue = yaml.safe_load((repo / "data" / "queue.yaml").read_text())["items"]
    assert len(queue) == 3
    # idempotente
    assert approve_batches(settings, now=SUNDAY) == []
    assert carousel["id"] in car["items"][0]


def test_due_posts(settings, repo, monkeypatch):
    _real_batch(settings, monkeypatch, 1, "feed")
    approve_batches(settings, now=SUNDAY)
    assert due_posts(settings, now=SUNDAY) == []
    assert len(due_posts(settings, now=datetime(2026, 10, 5, 19, 1, tzinfo=TZ))) == 1


def test_plan_for_today(settings):
    assert plan_for_today(settings, SUNDAY.date()) == [{"format": "feed", "count": 3}]
    assert plan_for_today(settings, datetime(2026, 10, 6).date()) == [{"format": "story", "count": 3}]
