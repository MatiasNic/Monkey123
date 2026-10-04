import json
import shutil
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from mono.llm.mock import MockLLM
from mono.pipeline import load_batch, plan_batch, render_batch
from mono.providers.image_mock import MockImageProvider
from mono.providers.video_slideshow import build_command
from mono.publish.instagram import build_reel_payload
from mono.publish.media_host import DryRunHost
from mono.publish.publisher import publish_due
from mono.scheduling import approve_batches

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg no instalado")
TZ = ZoneInfo("America/Argentina/Buenos_Aires")
SUNDAY = datetime(2026, 10, 4, 10, 0, tzinfo=TZ)
LATER = datetime(2026, 10, 20, 23, 0, tzinfo=TZ)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt,sample_rate:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_build_command_shape(tmp_path):
    imgs = [tmp_path / f"{i}.jpg" for i in range(3)]
    cmd = build_command(imgs, tmp_path / "o.mp4", seconds_per_image=2.5, fade=0.4, seed="x")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.count("zoompan") == 3 and graph.count("xfade") == 2
    assert "anullsrc=r=48000" in " ".join(cmd)
    assert cmd[cmd.index("-t", cmd.index("-filter_complex")) + 1] == "7.900"
    assert "+faststart" in cmd and "yuv420p" in cmd
    with pytest.raises(ValueError):
        build_command(imgs[:1], tmp_path / "o.mp4")


def test_reel_payload():
    p = build_reel_payload("https://x/v.mp4", "cap", ai=True, share_to_feed=True)
    assert p == {"video_url": "https://x/v.mp4", "media_type": "REELS", "share_to_feed": "true", "caption": "cap",
                 "is_ai_generated": "true"}


@pytest.fixture
def reel_batch(settings, repo, monkeypatch):
    monkeypatch.setattr("mono.pipeline.get_llm", lambda s, dry_run=False: MockLLM(s))
    monkeypatch.setattr("mono.pipeline.get_image_provider", lambda s, name=None, dry_run=False: MockImageProvider(s))
    return render_batch(settings, plan_batch(settings, 3, fmt="reel"))


@needs_ffmpeg
def test_reel_video_meets_instagram_specs(settings, repo, reel_batch):
    video = repo / reel_batch["video"]["file"]
    info = probe(video)
    streams = {s["codec_type"]: s for s in info["streams"]}
    assert streams["video"]["codec_name"] == "h264" and streams["video"]["pix_fmt"] == "yuv420p"
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)
    assert streams["video"]["r_frame_rate"] == "30/1"
    assert streams["audio"]["codec_name"] == "aac" and streams["audio"]["sample_rate"] == "48000"
    assert 3 <= float(info["format"]["duration"]) <= 90
    assert reel_batch["caption"] and all(i["caption"] == reel_batch["caption"] for i in reel_batch["items"])
    assert "Video del reel" in (repo / reel_batch["dir"] / "batch.md").read_text()


@needs_ffmpeg
def test_approve_rebuilds_video_without_discarded_images(settings, repo, reel_batch):
    (repo / reel_batch["items"][1]["files"]["final"]).unlink()
    created = approve_batches(settings, now=SUNDAY)
    assert [e["format"] for e in created] == ["reel"]
    assert created[0]["files"][0].endswith(".mp4")
    batch = load_batch(repo / reel_batch["dir"])
    assert batch["video"]["items"] == [reel_batch["items"][0]["id"], reel_batch["items"][2]["id"]]
    assert abs(float(probe(repo / batch["video"]["file"])["format"]["duration"]) - 5.4) < 0.2
    assert datetime.fromisoformat(created[0]["publish_at"]).weekday() == 6  # domingo


@needs_ffmpeg
def test_publish_reel(settings, repo, reel_batch):
    approve_batches(settings, now=SUNDAY)

    class IG:
        calls = []

        def publishing_quota(self):
            return 0, 100

        def create_container(self, payload):
            self.calls.append(payload)
            return "c1"

        def wait_ready(self, cid, timeout=None, interval=None):
            self.calls.append({"wait": cid, "timeout": timeout})

        def publish(self, cid):
            return "m1"

        def permalink(self, mid):
            return "https://instagram.com/reel/m1"

    ig, host = IG(), DryRunHost()
    done = publish_due(settings, now=LATER, client=ig, host=host)
    assert done[0]["status"] == "published"
    assert ig.calls[0]["media_type"] == "REELS" and ig.calls[0]["video_url"].endswith(".mp4")
    assert ig.calls[1]["timeout"] == settings.get("instagram.video_poll_timeout")
    assert host.deleted == host.uploaded
