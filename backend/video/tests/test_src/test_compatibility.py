"""Regression tests for fork/upstream video compatibility boundaries."""

import json
from types import SimpleNamespace

import fork_features.audio_tracks  # noqa: F401
from appsettings.src import reindex as reindex_module
from common.src import index_generic
from common.src.env_settings import EnvironmentSettings
from video.src import index as video_index
from video.src import media_streams, subtitle


def test_redownload_refreshes_enriched_streams_from_cache(  # noqa: C901
    monkeypatch, tmp_path
):
    """Force redownloads must refresh enriched streams from the download
    cache."""
    cache_dir = tmp_path / "cache"
    cache_file = cache_dir / "download" / "video.mp4"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"cached media")
    media_dir = tmp_path / "media"
    media_dir.mkdir()

    existing = {
        "youtube_id": "video",
        "media_url": "chan/video.mp4",
        "player": {
            "duration": 9,
            "duration_str": "0:09",
            "watched": True,
        },
        "date_downloaded": 123,
        "vid_type": "videos",
        "channel": {
            "channel_id": "chan",
            "channel_name": "Channel",
        },
    }
    config = {
        "downloads": {
            "container": "mp4",
            "extractor_lang": None,
            "integrate_ryd": False,
            "integrate_sponsorblock": False,
            "subtitle": None,
            "subtitle_source": "user",
            "subtitle_index": False,
            "cookie_import": False,
            "pot_provider_url": None,
        },
        "application": {},
    }
    metadata = {
        "id": "video",
        "channel_id": "chan",
        "title": "Refreshed title",
        "thumbnail": "https://example.test/video.jpg",
        "upload_date": "20260801",
        "categories": [],
        "tags": [],
    }
    stream = {
        "index": 1,
        "codec_type": "audio",
        "codec_name": "aac",
        "bit_rate": "128000",
        "channels": 2,
        "channel_layout": "stereo",
        "tags": {"language": "es", "title": "Spanish"},
    }
    uploads = []

    class _Config:
        def __init__(self):
            self.config = config

    class _YtWrap:
        def __init__(self, *_args, **_kwargs):
            pass

        def extract(self, *_args, **_kwargs):
            return metadata, None

    class _ElasticWrap:
        def __init__(self, path):
            self.path = path

        def get(self, **_kwargs):
            if self.path == "ta_video/_doc/video":
                return {"_source": existing}, 200
            if self.path == "ta_channel/_doc/chan":
                return {
                    "_source": {
                        "channel_id": "chan",
                        "channel_name": "Channel",
                    }
                }, 200
            raise AssertionError(f"unexpected Elasticsearch GET: {self.path}")

        def put(self, data, **_kwargs):
            uploads.append(data)
            return {}, 200

    def _ffprobe(command, **_kwargs):
        if command[-1] != str(cache_file):
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"streams": [stream]}),
        )

    monkeypatch.setattr(index_generic, "AppConfig", _Config)
    monkeypatch.setattr(reindex_module, "AppConfig", _Config)
    monkeypatch.setattr(index_generic, "YtWrap", _YtWrap)
    monkeypatch.setattr(index_generic, "ElasticWrap", _ElasticWrap)
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(media_dir))
    monkeypatch.setattr(media_streams.subprocess, "run", _ffprobe)
    monkeypatch.setattr(
        media_streams,
        "stat",
        lambda _path: SimpleNamespace(st_size=len(b"cached media")),
    )
    monkeypatch.setattr(video_index, "get_duration_sec", lambda _path: 9)
    monkeypatch.setattr(
        video_index, "get_duration_str", lambda _duration: "0:09"
    )

    result = video_index.index_new_video("video")

    assert result["streams"] == [
        {
            "bitrate": 128000,
            "codec": "aac",
            "index": 1,
            "type": "audio",
            "language": "es",
            "title": "Spanish",
            "channels": 2,
            "channel_layout": "stereo",
        }
    ]
    assert result["media_size"] == len(b"cached media")
    assert uploads[-1]["streams"] == result["streams"]


def test_empty_subtitle_response_skips_download_and_backs_off(monkeypatch):
    """An empty successful subtitle response must be skipped with backoff."""
    video = SimpleNamespace(
        youtube_id="video",
        config={
            "downloads": {
                "cookie_import": False,
                "subtitle_index": False,
            }
        },
    )
    response = SimpleNamespace(ok=True, text="")
    sleeps = []
    monkeypatch.setattr(
        subtitle.requests, "get", lambda *_args, **_kwargs: response
    )
    monkeypatch.setattr(
        subtitle, "rand_sleep", lambda config: sleeps.append(config)
    )

    relevant_subtitles = [
        {
            "url": "https://example.test/subtitle",
            "lang": "en",
            "source": "user",
            "media_url": "video.en.vtt",
            "name": "English",
        }
    ]
    result = subtitle.YoutubeSubtitle(video).download_subtitles(
        relevant_subtitles
    )

    assert result == []
    assert sleeps == [video.config]
