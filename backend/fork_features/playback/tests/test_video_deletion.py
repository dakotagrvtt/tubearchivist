"""Real deletion boundary tests for prepared playback artifacts."""

from types import SimpleNamespace

import pytest
from common.src import index_generic
from common.src.env_settings import EnvironmentSettings
from fork_features.playback import cache
from video.src import comments, subtitle
from video.src.index import YoutubeVideo


@pytest.fixture
def deletion(monkeypatch, tmp_path):
    """Keep deletion real while replacing ES/config and Redis boundaries."""
    media = tmp_path / "media"
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(media))
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(
        index_generic,
        "AppConfig",
        lambda: SimpleNamespace(config={"downloads": {"comment_max": "10"}}),
    )
    documents = {
        "ta_video/_doc/video": {
            "youtube_id": "video",
            "media_url": "channel/video.mkv",
            "subtitles": [{"media_url": "channel/video.en.vtt"}],
        },
        "ta_comment/_doc/video": {"youtube_id": "video"},
        "ta_video/_doc/neighbor": {"youtube_id": "neighbor"},
        "ta_comment/_doc/neighbor": {"youtube_id": "neighbor"},
    }
    indexed_subtitles = {"video", "neighbor"}

    class Elastic:
        def __init__(self, path):
            self.path = path

        def get(self, **_kwargs):
            return {"_source": documents[self.path]}, 200

        def delete(self, **_kwargs):
            documents.pop(self.path)
            return {}, 200

        def post(self, data):
            assert self.path == "ta_subtitle/_delete_by_query?refresh=true"
            indexed_subtitles.remove(
                data["query"]["term"]["youtube_id"]["value"]
            )
            return {}, 200

    for module in (index_generic, subtitle, comments):
        monkeypatch.setattr(module, "ElasticWrap", Elastic)

    statuses = {
        "playback:video": "ready",
        "hls:video": "ready",
        "playback:neighbor": "ready",
        "hls:neighbor": "ready",
        "playback:video:lock": "mp4-owner",
        "hls:video:lock": "hls-owner",
    }

    class Redis:
        def del_message(self, key):
            statuses.pop(key, None)

    monkeypatch.setattr(cache, "RedisArchivist", Redis)
    files = [
        media / "channel/video.mkv",
        media / "channel/video.en.vtt",
        cache_dir / "transcode/video.mp4",
        cache_dir / "transcode/video.mp4.part",
        cache_dir / "transcode/video.mp4.part.mp4",
        cache_dir / "hls/video/master.m3u8",
        cache_dir / "hls/video/video/segment_00000.ts",
        cache_dir / "hls/video.part/video/segment_00000.ts",
    ]
    preserved = [
        media / "channel/neighbor.mkv",
        cache_dir / "transcode/neighbor.mp4",
        cache_dir / "hls/neighbor/video/segment_00000.ts",
        cache_dir / "hls/video.a1b2c3.part/video/segment_00000.ts",
    ]
    for path in files + preserved:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"media")

    return SimpleNamespace(
        video=YoutubeVideo("video"),
        files=files,
        preserved=preserved,
        documents=documents,
        subtitles=indexed_subtitles,
        statuses=statuses,
    )


@pytest.mark.parametrize("missing_archive", [False, True])
def test_delete_clears_playback_even_without_archive(
    deletion, missing_archive
):
    """Deletion removes this video's copies without touching another's."""
    if missing_archive:
        deletion.files[0].unlink()

    deletion.video.delete_media_file()

    assert not any(path.exists() for path in deletion.files)
    assert all(path.read_bytes() == b"media" for path in deletion.preserved)
    assert set(deletion.documents) == {
        "ta_video/_doc/neighbor",
        "ta_comment/_doc/neighbor",
    }
    assert deletion.subtitles == {"neighbor"}
    assert deletion.statuses == {
        "playback:neighbor": "ready",
        "hls:neighbor": "ready",
        "playback:video:lock": "mp4-owner",
        "hls:video:lock": "hls-owner",
    }


def test_cache_failures_do_not_stop_metadata_deletion(
    deletion, monkeypatch, capsys
):
    """Filesystem and Redis failures remain best effort during deletion."""
    remove = cache.os.remove
    blocked = deletion.files[2]

    def remove_with_failure(path):
        if str(path) == str(blocked):
            raise PermissionError("read-only cache")
        return remove(path)

    def unavailable_redis():
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr(cache.os, "remove", remove_with_failure)
    monkeypatch.setattr(cache, "RedisArchivist", unavailable_redis)

    deletion.video.delete_media_file()

    assert blocked.read_bytes() == b"media"
    assert not any(path.exists() for path in deletion.files if path != blocked)
    assert set(deletion.documents) == {
        "ta_video/_doc/neighbor",
        "ta_comment/_doc/neighbor",
    }
    assert deletion.subtitles == {"neighbor"}
    output = capsys.readouterr().out
    assert "failed to remove playback cache" in output
    assert "failed to clear playback status" in output
