"""Regression tests for fork/upstream video compatibility boundaries."""

from types import SimpleNamespace

from video.src import index as video_index
from video.src import subtitle


def test_existing_video_redownload_refreshes_streams_from_download_cache(
    monkeypatch,
):
    """Force redownloads must use the cache-aware reindex stream refresh."""
    calls = []

    class _Video:
        def __init__(self, _youtube_id, **_kwargs):
            self.json_data = {"youtube_id": "video"}

        def get_from_es(self, **_kwargs):
            return None

    class _Reindex:
        def reindex_single_video(self, youtube_id, from_download=False):
            calls.append((youtube_id, from_download))
            return SimpleNamespace(
                json_data={"youtube_id": youtube_id, "streams": [{"index": 1}]}
            )

    monkeypatch.setattr(video_index, "YoutubeVideo", _Video)
    monkeypatch.setattr("appsettings.src.reindex.Reindex", _Reindex)

    result = video_index.index_new_video("video")

    assert calls == [("video", True)]
    assert result == {"youtube_id": "video", "streams": [{"index": 1}]}


def test_empty_subtitle_response_is_skipped_before_parsing(monkeypatch):
    """An empty successful subtitle response must not reach the JSON parser."""
    video = SimpleNamespace(
        youtube_id="video",
        config={"downloads": {"cookie_import": False}},
    )
    response = SimpleNamespace(ok=True, text="")
    monkeypatch.setattr(
        subtitle.requests, "get", lambda *_args, **_kwargs: response
    )
    monkeypatch.setattr(subtitle, "rand_sleep", lambda *_args: None)

    result = subtitle.YoutubeSubtitle(video)._make_request(
        "https://example.test/subtitle", "en"
    )

    assert result is None
