"""Tests for playback preparation lifecycle state."""

from pathlib import Path

import pytest
from common.src.env_settings import EnvironmentSettings
from fork_features.playback import tasks


@pytest.fixture(autouse=True)
def _playback_enabled(monkeypatch):
    monkeypatch.setattr(
        tasks,
        "AppConfig",
        lambda: type(
            "Config",
            (),
            {"config": {"application": {"enable_fork_playback": True}}},
        )(),
    )


class _Connection:
    def __init__(self):
        self.eval_calls = []
        self.set_calls = []

    def set(self, *args, **kwargs):
        self.set_calls.append((args, kwargs))
        return True

    def eval(self, *args):
        self.eval_calls.append(args)
        return 1


class _Redis:
    NAME_SPACE = "ta:"

    def __init__(self):
        self.conn = _Connection()
        self.messages = []
        self.deleted = []

    def set_message(self, key, message, expire=None):
        self.messages.append((key, message, expire))

    def del_message(self, key):
        self.deleted.append(key)


def test_lock_renewal_uses_owner_token_and_refreshes_status():
    """Only the current owner may extend a long-running transcode lease."""
    redis = _Redis()

    renewed = tasks._renew_playback_lock(
        redis, "ta:playback:video:lock", "playback:video", "owner"
    )

    assert renewed is True
    assert redis.conn.eval_calls == [
        (
            tasks.RENEW_LOCK_SCRIPT,
            1,
            "ta:playback:video:lock",
            "owner",
            tasks.PLAYBACK_LOCK_TTL,
        )
    ]
    assert redis.messages == [
        (
            "playback:video",
            {"status": "preparing"},
            tasks.PLAYBACK_LOCK_TTL,
        )
    ]


def test_missing_source_reports_failure_and_releases_lock(
    monkeypatch, tmp_path
):
    """A missing archive file must leave an actionable failed state."""
    redis = _Redis()
    monkeypatch.setattr(tasks, "RedisArchivist", lambda: redis)
    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(tmp_path))
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(tmp_path))

    result = tasks.prepare_playback.run("video", "missing/video.mkv")

    assert result == "failed"
    assert redis.messages[-1][1] == {
        "status": "failed",
        "error": "video source is missing",
    }
    assert redis.conn.eval_calls[-1][0] == tasks.RELEASE_LOCK_SCRIPT


def test_failed_ffmpeg_removes_partial_output(monkeypatch, tmp_path):
    """A failed transcode must not leave a cache artifact marked ready."""
    media = tmp_path / "media"
    cache = tmp_path / "cache"
    media.mkdir()
    cache.mkdir()
    (media / "video.mkv").write_bytes(b"source")
    redis = _Redis()
    monkeypatch.setattr(tasks, "RedisArchivist", lambda: redis)
    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(media))
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(cache))

    def fail_ffmpeg(command, *_args):
        Path(command[-1]).touch()
        return 1, True

    monkeypatch.setattr(tasks, "_run_ffmpeg_with_lease", fail_ffmpeg)
    monkeypatch.setattr(tasks, "_renew_playback_lock", lambda *_args: True)

    result = tasks.prepare_playback.run("video", "video.mkv")

    assert result == "failed"
    assert not (cache / "transcode" / "video.mp4.part.mp4").exists()
    assert redis.messages[-1][1]["status"] == "failed"


def test_disabled_playback_task_does_not_acquire_lock(monkeypatch):
    """A queued task must become a no-op after the feature is disabled."""
    redis = _Redis()
    monkeypatch.setattr(tasks, "RedisArchivist", lambda: redis)
    monkeypatch.setattr(
        tasks,
        "AppConfig",
        lambda: type(
            "Config",
            (),
            {"config": {"application": {"enable_fork_playback": False}}},
        )(),
    )

    assert tasks.prepare_playback.run("video", "video.mkv") == "disabled"
    assert redis.deleted == ["playback:video"]
    assert redis.conn.set_calls == []
