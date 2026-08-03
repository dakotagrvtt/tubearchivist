"""Tests for audio-track download preparation."""

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
