"""Tests for playback cache invalidation."""

from common.src.env_settings import EnvironmentSettings
from fork_features.playback import cache


class _Redis:
    def __init__(self):
        self.deleted = []

    def del_message(self, key):
        self.deleted.append(key)


def test_invalidate_removes_complete_and_partial_cache(monkeypatch, tmp_path):
    """Replacing source media cannot retain an older prepared artifact."""
    redis = _Redis()
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(cache, "RedisArchivist", lambda: redis)
    transcode = tmp_path / "transcode"
    transcode.mkdir()
    paths = [
        transcode / "video.mp4",
        transcode / "video.mp4.part",
        transcode / "video.mp4.part.mp4",
    ]
    for path in paths:
        path.write_bytes(b"stale")

    cache.invalidate_playback_cache("video")

    assert not any(path.exists() for path in paths)
    assert redis.deleted == ["playback:video"]
