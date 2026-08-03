"""Tests for playback path handling."""

import urllib.parse

from common.src.env_settings import EnvironmentSettings
from fork_features.playback.media_paths import (
    normalize_media_url,
    resolve_archived_media_path,
)


def test_normalize_processed_media_url(monkeypatch, tmp_path):
    """Convert the frontend media root back to an archive-relative path."""
    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(tmp_path))
    processed = urllib.parse.quote(f"{tmp_path}/channel/video with spaces.mp4")

    assert normalize_media_url(processed) == ("channel/video with spaces.mp4")


def test_resolve_exact_archived_media(monkeypatch, tmp_path):
    """Use the indexed path when it exists."""
    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(tmp_path))
    media_dir = tmp_path / "channel"
    media_dir.mkdir()
    media_path = media_dir / "video.mp4"
    media_path.write_bytes(b"video")

    resolved = resolve_archived_media_path("channel/video.mp4", "video")

    assert resolved == ("channel/video.mp4", str(media_path))


def test_resolve_stale_mkv_as_mp4(monkeypatch, tmp_path):
    """Fall back to the actual MP4 beside a stale indexed MKV path."""
    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(tmp_path))
    media_dir = tmp_path / "channel"
    media_dir.mkdir()
    media_path = media_dir / "video.mp4"
    media_path.write_bytes(b"video")

    resolved = resolve_archived_media_path("channel/video.mkv", "video")

    assert resolved == ("channel/video.mp4", str(media_path))


def test_reject_missing_and_escaping_media(monkeypatch, tmp_path):
    """Do not invent a path or escape the configured archive root."""
    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(tmp_path))

    assert resolve_archived_media_path("channel/video.mkv", "video") is None
    assert resolve_archived_media_path("../../etc/passwd", "video") is None
