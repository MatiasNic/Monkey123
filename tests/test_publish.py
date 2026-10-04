from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import yaml

from mono.llm.mock import MockLLM
from mono.pipeline import plan_batch, render_batch
from mono.providers.image_mock import MockImageProvider
from mono.publish.instagram import (
    InstagramClient,
    InstagramError,
    build_carousel_item_payload,
    build_carousel_payload,
    build_image_payload,
    build_story_payload,
)
from mono.publish.media_host import DryRunHost
from mono.publish.publisher import MAX_ATTEMPTS, publish_due
from mono.scheduling import approve_batches

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
SUNDAY = datetime(2026, 10, 4, 10, 0, tzinfo=TZ)
LATER = datetime(2026, 10, 20, 23, 0, tzinfo=TZ)


def test_payloads():
    img = build_image_payload("https://x/1.jpg", "hola", "alt", ai=True)
    assert img == {"image_url": "https://x/1.jpg", "caption": "hola", "alt_text": "alt", "is_ai_generated": "true"}
    story = build_story_payload("https://x/1.jpg")
    assert story["media_type"] == "STORIES" and "caption" not in story and story["is_ai_generated"] == "true"
    child = build_carousel_item_payload("https://x/1.jpg", "alt")
    assert child["is_carousel_item"] == "true" and "is_ai_generated" not in child and "caption" not in child
    parent = build_carousel_payload(["a", "b"], "cap")
    assert parent == {"media_type": "CAROUSEL", "children": "a,b", "caption": "cap", "is_ai_generated": "true"}
    assert "is_ai_generated" not in build_image_payload("u", ai=False)
    with pytest.raises(ValueError):
        build_carousel_payload(["a"])


class FakeResp:
    def __init__(self, data, status=200):
        self.data, self.status_code, self.text = data, status, str(data)

    def json(self):
        return self.data


class FakeHTTP:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.posts = []

    def get(self, url, params=None, timeout=None):
        return FakeResp({"status_code": self.statuses.pop(0)})

    def post(self, url, data=None, timeout=None):
        self.posts.append((url, data))
        return FakeResp({"error": {"message": "Invalid parameter"}}, 400)


def test_wait_ready_handles_states():
    InstagramClient("u", "t", http=FakeHTTP(["IN_PROGRESS", "FINISHED"]), sleep=lambda s: None).wait_ready("c")
    with pytest.raises(InstagramError, match="ERROR"):
        InstagramClient("u", "t", http=FakeHTTP(["ERROR"]), sleep=lambda s: None).wait_ready("c")
    with pytest.raises(InstagramError, match="timeout"):
        InstagramClient("u", "t", http=FakeHTTP(["IN_PROGRESS"] * 5), poll_seconds=1, poll_timeout=2,
                        sleep=lambda s: None).wait_ready("c")


def test_api_errors_raise_and_token_goes_in_body():
    http = FakeHTTP([])
    client = InstagramClient("123", "secret", api_version="v25.0", http=http)
    with pytest.raises(InstagramError, match="Invalid parameter"):
        client.create_container({"image_url": "u"})
    url, data = http.posts[0]
    assert url == "https://graph.instagram.com/v25.0/123/media"
    assert data["access_token"] == "secret"


class FakeIG:
    def __init__(self, fail_on=None, quota=(0, 100)):
        self.calls, self.fail_on, self.quota, self.n = [], fail_on, quota, 0

    def _id(self):
        self.n += 1
        return f"id{self.n}"

    def publishing_quota(self):
        return self.quota

    def create_container(self, payload):
        if self.fail_on and self.fail_on in payload.get("media_type", "IMAGE"):
            raise InstagramError("boom")
        self.calls.append(("create", payload))
        return self._id()

    def wait_ready(self, cid):
        self.calls.append(("wait", cid))

    def publish(self, cid):
        self.calls.append(("publish", cid))
        return self._id()

    def permalink(self, mid):
        return f"https://instagram.com/p/{mid}"


@pytest.fixture
def queued(settings, repo, monkeypatch):
    monkeypatch.setattr("mono.pipeline.get_llm", lambda s, dry_run=False: MockLLM(s))
    monkeypatch.setattr("mono.pipeline.get_image_provider", lambda s, name=None, dry_run=False: MockImageProvider(s))
    for fmt, n in (("feed", 1), ("story", 1), ("carousel", 3)):
        render_batch(settings, plan_batch(settings, n, fmt=fmt))
    return approve_batches(settings, now=SUNDAY)


def _queue(repo):
    return yaml.safe_load((repo / "data" / "queue.yaml").read_text())["items"]


def test_publish_due_publishes_all_formats(settings, repo, queued):
    ig, host = FakeIG(), DryRunHost()
    done = publish_due(settings, now=LATER, client=ig, host=host)
    assert sorted(e["format"] for e in done) == ["carousel", "feed", "story"]
    assert all(e["status"] == "published" and e["permalink"] for e in _queue(repo))
    created = [p for name, p in ig.calls if name == "create"]
    assert sum(1 for p in created if p.get("is_carousel_item") == "true") == 3
    assert any(p.get("media_type") == "CAROUSEL" and p["children"].count(",") == 2 for p in created)
    assert any(p.get("media_type") == "STORIES" for p in created)
    assert sorted(host.uploaded) == sorted(host.deleted) and len(host.uploaded) == 5
    history = (repo / "data" / "history.jsonl").read_text()
    assert history.count('"status": "published"') == 5


def test_publish_due_only_due(settings, repo, queued):
    assert publish_due(settings, now=SUNDAY, client=FakeIG(), host=DryRunHost()) == []


def test_failure_retries_then_marks_failed_and_cleans_up(settings, repo, queued):
    host = DryRunHost()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        publish_due(settings, now=LATER, client=FakeIG(fail_on="STORIES"), host=host)
        story = next(e for e in _queue(repo) if e["format"] == "story")
        assert story["attempts"] == attempt and "boom" in story["last_error"]
    assert story["status"] == "failed"
    assert sorted(host.uploaded) == sorted(host.deleted)


def test_no_quota_publishes_nothing(settings, repo, queued):
    ig = FakeIG(quota=(100, 100))
    publish_due(settings, now=LATER, client=ig, host=DryRunHost())
    assert ig.calls == []
    assert all(e["status"] == "queued" for e in _queue(repo))


def test_dry_run_writes_nothing(settings, repo, queued):
    before = (repo / "data" / "queue.yaml").read_text()
    done = publish_due(settings, now=LATER, dry_run=True)
    assert len(done) == 3
    assert (repo / "data" / "queue.yaml").read_text() == before


def test_publish_specific_id(settings, repo, queued):
    target = queued[0]["id"]
    done = publish_due(settings, now=SUNDAY, only_id=target, client=FakeIG(), host=DryRunHost())
    assert [e["id"] for e in done] == [target]
