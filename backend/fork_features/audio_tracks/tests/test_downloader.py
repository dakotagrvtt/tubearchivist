"""Tests for audio-track download preparation."""

import shutil

from fork_features.audio_tracks import downloader


def _audio_format(language: str) -> dict:
    return {
        "format_id": f"audio-{language}",
        "language": language,
        "vcodec": "none",
        "acodec": "opus",
        "protocol": "https",
        "tbr": 128,
    }


class _ExtractWrap:
    def __init__(self, _obs, _config):
        pass

    @staticmethod
    def extract(_url):
        return {"formats": [_audio_format("es")]}, None


def _stub_multistream_resolution(monkeypatch):
    formats = [_audio_format("en"), _audio_format("es")]
    monkeypatch.setattr(
        downloader,
        "resolve_requested_audio_languages",
        lambda *_args: (["en", "es"], formats),
    )


def _remove_staging_directory(context):
    staging_directory = context.get("temp_dir")
    if staging_directory:
        shutil.rmtree(staging_directory, ignore_errors=True)


def test_single_explicit_language_is_staged(monkeypatch, tmp_path):
    """A single explicit request must not be treated as auto-discovery."""
    monkeypatch.setattr(downloader, "YtWrap", _ExtractWrap)
    monkeypatch.setattr(
        downloader,
        "resolve_requested_audio_languages",
        lambda *_args: (["es"], None),
    )
    obs = {
        "outtmpl": str(tmp_path / "%(id)s.%(ext)s"),
        "merge_output_format": "mkv",
    }

    context = downloader.AudioTracksDownloadHook().pre_download(
        obs, "video", "channel", {"downloads": {}}, {}
    )

    assert context["extra_formats"] == {"es": "audio-es"}
    assert context["main_path"] == str(tmp_path / "video.mkv")


def test_single_discovered_language_is_skipped(monkeypatch, tmp_path):
    """Do not append the only automatically discovered primary language."""
    formats = [_audio_format("en")]
    monkeypatch.setattr(
        downloader,
        "resolve_requested_audio_languages",
        lambda *_args: (["en"], formats),
    )

    context = downloader.AudioTracksDownloadHook().pre_download(
        {"outtmpl": str(tmp_path / "%(id)s.%(ext)s")},
        "video",
        "channel",
        {"downloads": {}},
        {},
    )

    assert context == {}


def test_primary_format_is_preserved_for_multiple_audio_tracks(
    monkeypatch, tmp_path
):
    """Additional audio preparation must not replace the primary selector."""
    _stub_multistream_resolution(monkeypatch)
    selector = "bestvideo[height<=480]+bestaudio/best[height<=480]"
    obs = {
        "format": selector,
        "outtmpl": str(tmp_path / "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
    }

    context = downloader.AudioTracksDownloadHook().pre_download(
        obs, "video", "channel", {"downloads": {}}, {}
    )

    try:
        assert obs["format"] == selector
    finally:
        _remove_staging_directory(context)


def test_primary_format_is_not_added_by_audio_hook(monkeypatch, tmp_path):
    """Audio preparation must not invent a primary selector."""
    _stub_multistream_resolution(monkeypatch)
    obs = {
        "outtmpl": str(tmp_path / "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
    }

    context = downloader.AudioTracksDownloadHook().pre_download(
        obs, "video", "channel", {"downloads": {}}, {}
    )

    try:
        assert "format" not in obs
    finally:
        _remove_staging_directory(context)
