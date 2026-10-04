import glob
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from typer.testing import CliRunner

from mono.cli import app
from mono.doctor import run_checks, status_summary
from mono.maintenance import prune_media, record_token_refresh, token_days_left
from mono.notify import _email, _github_issue, _telegram, notify

UTC = timezone.utc


class Resp:
    def __init__(self, data=None, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeGitHub:
    def __init__(self, existing):
        self.existing, self.posts = existing, []

    def get(self, url, headers=None, params=None, timeout=None):
        assert params["labels"] == "alerta"
        return Resp(self.existing)

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append((url, json))
        return Resp({"number": 7}, 201)


@pytest.fixture
def gh_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")


def test_github_issue_dedup_comments_on_existing(settings, gh_env):
    http = FakeGitHub([{"number": 3, "title": "publish.yml falló"}])
    assert _github_issue(settings, "failure", "publish.yml falló", "otra vez", http=http) == "comentado en #3"
    assert http.posts[0][0].endswith("/issues/3/comments")


def test_github_issue_creates_new_with_labels(settings, gh_env):
    http = FakeGitHub([{"number": 3, "title": "otra cosa"}, {"number": 4, "title": "x", "pull_request": {}}])
    assert _github_issue(settings, "failure", "x", "body", http=http) == "issue #7"
    assert http.posts[0][1]["labels"] == ["alerta", "failure"]


def test_missing_credentials_are_skipped(settings, monkeypatch):
    for key in ("GITHUB_TOKEN", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
        monkeypatch.delenv(key, raising=False)
    settings.data["notifications"] = {"channels": ["github_issue", "email", "telegram"], "events": ["failure"]}
    results = notify(settings, "failure", "t", "b")
    assert all(r.startswith("salteado") for r in results.values()) and len(results) == 3


def test_event_filter_and_unknown_event(settings):
    settings.data["notifications"] = {"channels": ["github_issue"], "events": ["failure"]}
    assert notify(settings, "published", "t") == {}
    with pytest.raises(ValueError):
        notify(settings, "nope", "t")


def test_channel_errors_never_raise(settings):
    def boom(*a, **k):
        raise RuntimeError("caído")
    settings.data["notifications"] = {"channels": ["github_issue"], "events": ["failure"]}
    assert notify(settings, "failure", "t", channels={"github_issue": boom})["github_issue"].startswith("error")


def test_email_and_telegram(settings, monkeypatch):
    for k, v in {"SMTP_HOST": "smtp.x", "SMTP_USER": "u@x", "SMTP_PASSWORD": "p", "NOTIFY_EMAIL_TO": "me@x",
                 "TELEGRAM_BOT_TOKEN": "bt", "TELEGRAM_CHAT_ID": "42"}.items():
        monkeypatch.setenv(k, v)
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent.append((host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, u, p):
            sent.append(("login", u))

        def send_message(self, msg):
            sent.append(msg["Subject"])

    assert _email(settings, "failure", "Falló", "b", smtp_cls=FakeSMTP) == "email a me@x"
    assert sent == [("smtp.x", 587), ("login", "u@x"), "[mono] Falló"]

    class FakeHTTP:
        def post(self, url, json=None, timeout=None):
            assert url.endswith("/botbt/sendMessage") and json["chat_id"] == "42"
            return Resp({"ok": True})

    assert _telegram(settings, "failure", "t", "b", http=FakeHTTP()) == "telegram 42"


def test_token_status_and_check(settings, repo):
    now = datetime(2026, 10, 5, tzinfo=UTC)
    assert token_days_left(settings, now) is None
    record_token_refresh(settings, 60 * 86400, now=now)
    assert round(token_days_left(settings, now)) == 60
    assert round(token_days_left(settings, now + timedelta(days=55))) == 5


def test_refresh_token_write_to_is_private(settings, repo, tmp_path):
    out = tmp_path / "tok"
    result = CliRunner().invoke(app, ["refresh-token", "--dry-run", "--write-to", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_text() == "DRY_TOKEN_REFRESHED"
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600
    assert "DRY_TOKEN_REFRESHED" not in result.output


def test_doctor_reports_missing_env(settings, monkeypatch):
    for key in ("IG_USER_ID", "IG_ACCESS_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    checks = {c.name: c for c in run_checks(settings)}
    assert not checks["IG_USER_ID, IG_ACCESS_TOKEN"].ok
    monkeypatch.setenv("IG_USER_ID", "1")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "t")
    assert {c.name: c for c in run_checks(settings)}["IG_USER_ID, IG_ACCESS_TOKEN"].ok
    (settings.root / "drafts").mkdir(exist_ok=True)
    assert any(line.startswith("Cola:") for line in status_summary(settings))


def _batch(root, name, statuses, created):
    folder = root / "drafts" / name
    folder.mkdir(parents=True)
    items = [{"id": f"{name}-{i}", "status": s, "created_at": created.isoformat()} for i, s in enumerate(statuses)]
    (folder / "batch.yaml").write_text(yaml.safe_dump({"id": name, "items": items}))
    for i in range(len(statuses)):
        (folder / f"{name}-{i}.jpg").write_bytes(b"x")
    return folder


def test_prune_only_old_finished_batches(settings, repo):
    now = datetime(2026, 12, 31, tzinfo=UTC)
    old_done = _batch(repo, "old", ["published", "discarded"], now - timedelta(days=90))
    old_pending = _batch(repo, "pend", ["published", "queued"], now - timedelta(days=90))
    recent = _batch(repo, "new", ["published"], now - timedelta(days=5))
    assert len(prune_media(settings, 60, now=now, dry_run=True)) == 2
    assert (old_done / "old-0.jpg").exists()
    removed = prune_media(settings, 60, now=now)
    assert {p.name for p in removed} == {"old-0.jpg", "old-1.jpg"}
    assert (old_done / "batch.yaml").exists() and "pruned_at" in (old_done / "batch.yaml").read_text()
    assert (old_pending / "pend-0.jpg").exists() and (recent / "new-0.jpg").exists()


def test_queue_count_cli(settings, repo):
    (repo / "data" / "queue.yaml").write_text("items: []\n")
    result = CliRunner().invoke(app, ["queue", "--due", "--count"])
    assert result.exit_code == 0 and result.output.strip() == "0"


def test_workflows_are_valid_yaml():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    files = glob.glob(str(root / ".github" / "workflows" / "*.yml"))
    assert len(files) >= 7
    for f in files:
        data = yaml.safe_load(open(f))
        assert "jobs" in data and (True in data or "on" in data)  # PyYAML lee `on:` como True
