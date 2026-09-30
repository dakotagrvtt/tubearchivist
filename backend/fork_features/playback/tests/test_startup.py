"""Tests for playback startup setup and cleanup."""

import os

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


def test_ensure_cache_directory_reclaims_abandoned_hls_staging(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(tmp_path))
    hls = tmp_path / "hls"
    abandoned = hls / "video.worker-token.part"
    abandoned.mkdir(parents=True)
    (abandoned / "segment.ts").write_bytes(b"abandoned")
    legacy_staging = hls / "video.part"
    legacy_staging.mkdir()
    (legacy_staging / "segment.ts").write_bytes(b"legacy")
    completed = hls / "completed"
    completed.mkdir()
    playlist = completed / "master.m3u8"
    playlist.write_text("completed")
    transcode = tmp_path / "transcode"
    transcode.mkdir()
    mp4 = transcode / "video.mp4"
    mp4.write_bytes(b"transcode")

    startup.ensure_cache_directory()

    assert not abandoned.exists()
    assert not legacy_staging.exists()
    assert playlist.read_text() == "completed"
    assert mp4.read_bytes() == b"transcode"


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
    os.utime(hls / "old", (1, 1))

    assert startup.cleanup_hls_cache(max_age_seconds=10) == 1
    assert not (hls / "old").exists()


def test_cleanup_hls_cache_preserves_staging_under_age_pressure(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(startup.time, "time", lambda: 1000)
    hls = tmp_path / "hls"
    staging = hls / "active.part"
    staging.mkdir(parents=True)
    segment = staging / "segment.ts"
    segment.write_bytes(b"active")
    old = hls / "old"
    old.mkdir()
    (old / "master.m3u8").write_text("old")
    recent = hls / "recent"
    recent.mkdir()
    (recent / "master.m3u8").write_text("recent")
    os.utime(staging, (1, 1))
    os.utime(old, (1, 1))
    os.utime(recent, (1000, 1000))

    removed = startup.cleanup_hls_cache(max_age_seconds=10)

    assert segment.is_file()
    assert segment.read_bytes() == b"active"
    assert not old.exists()
    assert recent.is_dir()
    assert removed == 1


def test_cleanup_hls_cache_preserves_staging_under_size_pressure(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(startup.time, "time", lambda: 1000)
    hls = tmp_path / "hls"
    staging = hls / "active.worker-token.part"
    staging.mkdir(parents=True)
    segment = staging / "segment.ts"
    segment.write_bytes(b"a" * 16)
    old = hls / "old"
    old.mkdir()
    (old / "master.m3u8").write_bytes(b"o" * 6)
    recent = hls / "recent"
    recent.mkdir()
    (recent / "master.m3u8").write_bytes(b"r" * 6)
    os.utime(staging, (100, 100))
    os.utime(old, (200, 200))
    os.utime(recent, (300, 300))

    removed = startup.cleanup_hls_cache(max_bytes=10)

    assert segment.is_file()
    assert segment.read_bytes() == b"a" * 16
    assert not old.exists()
    assert recent.is_dir()
    assert removed == 1


def test_cleanup_hls_cache_excludes_staging_from_size_budget(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(startup.time, "time", lambda: 1000)
    hls = tmp_path / "hls"
    completed = hls / "completed"
    completed.mkdir(parents=True)
    playlist = completed / "master.m3u8"
    playlist.write_bytes(b"c" * 6)
    staging = hls / "active.part"
    staging.mkdir()
    segment = staging / "segment.ts"
    segment.write_bytes(b"a" * 16)
    os.utime(completed, (100, 100))
    os.utime(staging, (200, 200))

    removed = startup.cleanup_hls_cache(max_bytes=10)

    assert playlist.is_file()
    assert playlist.read_bytes() == b"c" * 6
    assert segment.is_file()
    assert removed == 0
