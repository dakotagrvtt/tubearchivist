"""Tests for interrupted audio staging cleanup."""

from fork_features.audio_tracks import startup


def test_clear_only_audio_staging_directories(monkeypatch, tmp_path):
    """Reclaim feature staging without touching unrelated temporary data."""
    stale = tmp_path / "ta-audio-video-123"
    stale.mkdir()
    (stale / "track.webm").write_bytes(b"audio")
    unrelated = tmp_path / "keep-me"
    unrelated.mkdir()
    monkeypatch.setattr(startup.tempfile, "gettempdir", lambda: str(tmp_path))

    removed = startup.clear_stale_staging_directories()

    assert removed == 1
    assert not stale.exists()
    assert unrelated.exists()
