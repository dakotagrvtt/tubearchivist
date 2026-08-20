"""Tests for playback startup setup and cleanup."""

from common.src.env_settings import EnvironmentSettings
from fork_features.playback import startup


class _Connection:
    def __init__(self):
        self.deleted = []

    @staticmethod
    def scan_iter(match):
        if match == "ta:playback:*":
            return [b"ta:playback:one", b"ta:playback:one:lock"]
        assert match == "ta:hls:*"
        return [b"ta:hls:one"]

    def delete(self, key):
        self.deleted.append(key)
        return 1


class _Redis:
    NAME_SPACE = "ta:"

    def __init__(self):
        self.conn = _Connection()


def test_ensure_cache_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(tmp_path))

    startup.ensure_cache_directory()

    assert (tmp_path / "transcode").is_dir()


def test_clear_playback_redis_state():
    redis = _Redis()

    removed = startup.clear_redis_state(redis)

    assert removed == 3
    assert redis.conn.deleted == [
        b"ta:playback:one",
        b"ta:playback:one:lock",
        b"ta:hls:one",
    ]


def test_cleanup_hls_cache_removes_old_presentations(monkeypatch, tmp_path):
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(tmp_path))
    hls = tmp_path / "hls"
    hls.mkdir()
    (hls / "old").mkdir()
    (hls / "old" / "master.m3u8").write_text("old")
    import os

    os.utime(hls / "old", (1, 1))

    assert startup.cleanup_hls_cache(max_age_seconds=10) == 1
    assert not (hls / "old").exists()
