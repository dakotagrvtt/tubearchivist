"""Tests for playback status and accelerated responses."""

import pytest
from fork_features.playback import views


@pytest.fixture(autouse=True)
def _playback_enabled(monkeypatch):
    monkeypatch.setattr(
        views,
        "AppConfig",
        lambda: type(
            "Config",
            (),
            {"config": {"application": {"enable_fork_playback": True}}},
        )(),
    )


class _View:
    status_code = 200
    response = {"media_url": "channel/video.mkv"}

    def get_document(self, _video_id):
        pass


class _Connection:
    def __init__(self, locked=False):
        self.locked = locked

    def exists(self, _key):
        return self.locked


class _Redis:
    NAME_SPACE = "ta:"

    def __init__(self, status=None, locked=False):
        self.status = status or {}
        self.conn = _Connection(locked)
        self.messages = []

    def get_message_dict(self, _key):
        return self.status

    def set_message(self, key, message, expire=None):
        self.messages.append((key, message, expire))


def test_completed_cache_is_authoritative(monkeypatch):
    """Disk readiness wins even when Redis state expired."""
    monkeypatch.setattr(views, "playback_cache_ready", lambda _id: True)

    assert views.PlaybackViewHandler._status_response("video") == {
        "status": "ready"
    }


def test_stale_ready_status_returns_pending(monkeypatch):
    """A Redis ready marker cannot outlive a deleted cache artifact."""
    monkeypatch.setattr(views, "playback_cache_ready", lambda _id: False)
    monkeypatch.setattr(
        views,
        "RedisArchivist",
        lambda: _Redis({"status": "ready"}),
    )

    assert views.PlaybackViewHandler._status_response("video") == {
        "status": "pending"
    }


def test_existing_lock_returns_preparing(monkeypatch):
    monkeypatch.setattr(views, "playback_cache_ready", lambda _id: False)
    monkeypatch.setattr(views, "RedisArchivist", lambda: _Redis(locked=True))

    assert views.PlaybackViewHandler._status_response("video") == {
        "status": "preparing"
    }


def test_mp4_stream_uses_internal_redirect(monkeypatch, tmp_path):
    """An archived MP4 is served by Nginx without preparation."""

    class FakeResponse(dict):
        def __init__(self, status):
            super().__init__()
            self.status_code = status
            self.content = None

    media_path = tmp_path / "video.mp4"
    media_path.write_bytes(b"video")
    monkeypatch.setattr(
        views,
        "resolve_archived_media_path",
        lambda *_args: ("channel/video.mp4", str(media_path)),
    )
    monkeypatch.setattr(
        views.PlaybackViewHandler,
        "_repair_media_url",
        lambda *_args: None,
    )
    monkeypatch.setattr(views, "HttpResponse", FakeResponse)
    request = type("Request", (), {"method": "GET"})()

    response = views.PlaybackViewHandler(_View()).stream(request, "video")

    assert response.status_code == 200
    assert response["X-Accel-Redirect"] == (
        "/protected-media/channel/video.mp4"
    )


def test_non_mp4_stream_queues_preparation(monkeypatch, tmp_path):
    """A pending non-MP4 request queues work and returns retry guidance."""

    class FakeResponse(dict):
        def __init__(self, data, status=200):
            super().__init__()
            self.data = data
            self.status_code = status

    class FakeTask:
        calls = []

        @classmethod
        def delay(cls, *args):
            cls.calls.append(args)

    redis = _Redis()
    media_path = tmp_path / "video.mkv"
    media_path.write_bytes(b"video")
    monkeypatch.setattr(
        views,
        "resolve_archived_media_path",
        lambda *_args: ("channel/video.mkv", str(media_path)),
    )
    monkeypatch.setattr(views, "playback_cache_ready", lambda _id: False)
    monkeypatch.setattr(views, "RedisArchivist", lambda: redis)
    monkeypatch.setattr(views, "prepare_playback", FakeTask)
    monkeypatch.setattr(views, "Response", FakeResponse)
    request = type("Request", (), {"method": "GET"})()

    response = views.PlaybackViewHandler(_View()).stream(request, "video")

    assert response.status_code == 202
    assert response["Retry-After"] == "5"
    assert FakeTask.calls == [("video", "channel/video.mkv")]
    assert redis.messages[-1] == (
        "playback:video",
        {"status": "preparing"},
        300,
    )


def test_disabled_playback_does_not_read_media_or_queue(monkeypatch):
    """The master switch must stop the fork endpoint before any work starts."""

    class FakeResponse(dict):
        def __init__(self, data, status=200):
            super().__init__()
            self.data = data
            self.status_code = status

    monkeypatch.setattr(
        views,
        "AppConfig",
        lambda: type(
            "Config",
            (),
            {"config": {"application": {"enable_fork_playback": False}}},
        )(),
    )
    monkeypatch.setattr(views, "Response", FakeResponse)
    handler = views.PlaybackViewHandler(_View())

    response = handler.stream(
        type("Request", (), {"method": "GET"})(), "video"
    )

    assert response.status_code == 404
    assert response.data == {"error": "enhanced playback is disabled"}


@pytest.mark.parametrize(
    ("status", "locked", "expected_calls"),
    [
        ({"status": "preparing"}, False, 1),
        ({"status": "preparing"}, True, 0),
        ({"status": "queued"}, False, 0),
    ],
)
def test_hls_request_tracks_queue_and_worker_lifecycle(
    monkeypatch, tmp_path, status, locked, expected_calls
):
    class HlsView(_View):
        response = {
            "media_url": "channel/video.mkv",
            "streams": [
                {"type": "audio", "index": 1, "language": "en"},
                {"type": "audio", "index": 2, "language": "es"},
            ],
        }

    class FakeResponse(dict):
        def __init__(self, data, status=200):
            super().__init__()
            self.data = data
            self.status_code = status

    class FakeTask:
        calls = []

        @classmethod
        def delay(cls, *args):
            cls.calls.append(args)

    redis = _Redis(status, locked=locked)
    media_path = tmp_path / "video.mkv"
    media_path.write_bytes(b"video")
    monkeypatch.setattr(
        views,
        "resolve_archived_media_path",
        lambda *_args: ("channel/video.mkv", str(media_path)),
    )
    monkeypatch.setattr(
        views, "hls_asset_path", lambda *_args: str(tmp_path / "missing")
    )
    monkeypatch.setattr(views, "RedisArchivist", lambda: redis)
    monkeypatch.setattr(views, "prepare_hls_playback", FakeTask)
    monkeypatch.setattr(views, "Response", FakeResponse)

    response = views.PlaybackViewHandler(HlsView()).hls(
        type("Request", (), {"method": "GET"})(), "video"
    )

    assert response.status_code == 202
    assert len(FakeTask.calls) == expected_calls
    if expected_calls:
        assert FakeTask.calls == [
            (
                "video",
                "channel/video.mkv",
                HlsView.response["streams"],
            )
        ]
        assert redis.messages[-1] == (
            "hls:video",
            {"status": "queued"},
            300,
        )
    else:
        assert redis.messages == []
