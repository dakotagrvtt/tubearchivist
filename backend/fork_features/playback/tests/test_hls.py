from pathlib import Path
from types import SimpleNamespace

from common.src.env_settings import EnvironmentSettings
from fork_features.playback import hls


def test_build_hls_command_maps_each_audio_stream():
    command = hls.build_hls_command(
        "/youtube/video.mkv",
        "/cache/hls/video.part",
        [
            {"index": 1, "language": "en", "title": "English"},
            {"index": 3, "language": "es", "title": "Español"},
        ],
    )

    assert "-map" in command
    assert command[command.index("-map") + 1] == "0:v:0"
    assert "0:1" in command
    assert "0:3" in command
    assert "-an" in command
    assert command[-1].endswith("audio1/index.m3u8")


def test_hls_task_disabled_clears_status(monkeypatch):
    class Redis:
        def __init__(self):
            self.deleted = []

        def del_message(self, key):
            self.deleted.append(key)

    redis = Redis()
    monkeypatch.setattr(hls, "RedisArchivist", lambda: redis)
    monkeypatch.setattr(
        hls,
        "AppConfig",
        lambda: type("Config", (), {"config": {"application": {}}})(),
    )
    monkeypatch.setattr(hls, "is_feature_enabled", lambda *_args: False)

    assert hls.prepare_hls_playback.run("video", "video.mkv", []) == "disabled"
    assert redis.deleted == ["hls:video"]


def test_hls_cache_ready_requires_master_file(monkeypatch, tmp_path):
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(tmp_path))
    assert not hls.hls_cache_ready("video")
    master = Path(hls.hls_master_path("video"))
    master.parent.mkdir(parents=True)
    master.write_text("#EXTM3U")
    assert hls.hls_cache_ready("video")


def test_hls_task_enforces_cache_limits_after_generation(
    monkeypatch, tmp_path
):
    class Connection:
        @staticmethod
        def set(*_args, **_kwargs):
            return True

        @staticmethod
        def eval(*_args, **_kwargs):
            return 1

    class Redis:
        NAME_SPACE = "ta:"

        def __init__(self):
            self.conn = Connection()
            self.messages = []

        def set_message(self, key, message, expire=None):
            self.messages.append((key, message, expire))

    redis = Redis()
    media = tmp_path / "media"
    cache = tmp_path / "cache"
    source = media / "channel" / "video.mkv"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    cleanup_calls = []

    def run_ffmpeg(*_args, **_kwargs):
        output = cache / "hls" / "video.part" / "video"
        (output / "index.m3u8").write_text("#EXTM3U")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(media))
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(cache))
    monkeypatch.setattr(hls, "RedisArchivist", lambda: redis)
    monkeypatch.setattr(
        hls,
        "AppConfig",
        lambda: type("Config", (), {"config": {"application": {}}})(),
    )
    monkeypatch.setattr(hls, "is_feature_enabled", lambda *_args: True)
    monkeypatch.setattr(hls.subprocess, "run", run_ffmpeg)
    monkeypatch.setattr(
        hls, "cleanup_hls_cache", lambda: cleanup_calls.append(True)
    )

    result = hls.prepare_hls_playback.run(
        "video",
        "channel/video.mkv",
        [
            {"type": "audio", "index": 1, "language": "en"},
            {"type": "audio", "index": 2, "language": "es"},
        ],
    )

    assert result == "ready"
    assert cleanup_calls == [True]
    assert redis.messages[-1][1] == {"status": "ready"}


def test_video_tasks_reexports_hls_task_for_celery_discovery():
    from video import tasks as video_tasks

    assert video_tasks.prepare_hls_playback is hls.prepare_hls_playback
