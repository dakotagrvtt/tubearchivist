"""Request handling for fork-owned range-capable playback."""

from __future__ import annotations

import mimetypes
from typing import Any

from common.serializers import ErrorResponseSerializer
from common.src.es_connect import ElasticWrap
from common.src.ta_redis import RedisArchivist
from django.http import HttpResponse
from fork_features.playback.media_paths import (
    normalize_media_url,
    resolve_archived_media_path,
)
from fork_features.playback.tasks import (
    playback_cache_ready,
    playback_lock_key,
    playback_status_key,
    prepare_playback,
)
from rest_framework.response import Response


class PlaybackViewHandler:
    """Keep fork playback behavior behind a small core-view hook."""

    def __init__(self, view: Any):
        self.view = view

    @staticmethod
    def _repair_media_url(video_id: str, media_url: str) -> None:
        """Persist a safe extension correction without blocking playback."""
        try:
            _, status_code = ElasticWrap(f"ta_video/_update/{video_id}").post(
                {"doc": {"media_url": media_url}}
            )
        except Exception as error:  # pragma: no cover - ES boundary
            print(f"{video_id}: failed to repair media path: {error}")
            return

        if status_code not in (200, 201):
            print(f"{video_id}: failed to repair media path")

    def _get_media(self, video_id: str):
        """Return the indexed media URL and safe source path."""
        self.view.get_document(video_id)
        if self.view.status_code == 404 or not isinstance(
            self.view.response, dict
        ):
            return (
                None,
                None,
                Response(
                    ErrorResponseSerializer({"error": "video not found"}).data,
                    status=404,
                ),
            )

        media_url = self.view.response.get("media_url")
        if not media_url:
            return (
                None,
                None,
                Response(
                    ErrorResponseSerializer(
                        {
                            "error": (
                                "Video media path is missing from the index."
                            )
                        }
                    ).data,
                    status=404,
                ),
            )

        indexed_media_url = normalize_media_url(media_url)
        resolved = resolve_archived_media_path(media_url, video_id)
        if not resolved:
            return (
                None,
                None,
                Response(
                    ErrorResponseSerializer(
                        {"error": "Video file is missing from the archive."}
                    ).data,
                    status=404,
                ),
            )

        resolved_media_url, media_path = resolved
        if resolved_media_url != indexed_media_url:
            self._repair_media_url(video_id, resolved_media_url)

        return resolved_media_url, media_path, None

    @staticmethod
    def _redirect(request, uri: str, content_type: str):
        """Ask the front proxy to serve a protected range-capable file."""
        response = HttpResponse(status=200)
        response["X-Accel-Redirect"] = uri
        response["Content-Type"] = content_type
        response["Accept-Ranges"] = "bytes"
        if request.method == "HEAD":
            response.content = b""
        return response

    @staticmethod
    def _status_response(video_id: str):
        """Read preparation state without starting a new task."""
        if playback_cache_ready(video_id):
            return {"status": "ready"}

        redis = RedisArchivist()
        status = redis.get_message_dict(playback_status_key(video_id))
        lock_key = redis.NAME_SPACE + playback_lock_key(video_id)
        if redis.conn.exists(lock_key):
            return {"status": "preparing"}
        if status.get("status") == "ready":
            return {"status": "pending"}
        return status or {"status": "pending"}

    def stream(self, request, video_id: str):
        """Return an accelerated stream or queue browser preparation."""
        media_url, media_path, error = self._get_media(video_id)
        if error:
            return error

        if media_url.lower().endswith(".mp4"):
            return self._redirect(
                request,
                f"/protected-media/{media_url}",
                mimetypes.guess_type(media_path)[0] or "video/mp4",
            )

        if playback_cache_ready(video_id):
            return self._redirect(
                request,
                f"/protected-transcode/{video_id}.mp4",
                "video/mp4",
            )

        status = self._status_response(video_id)
        if status.get("status") == "failed":
            return Response(
                ErrorResponseSerializer(
                    {
                        "error": status.get(
                            "error", "playback preparation failed"
                        )
                    }
                ).data,
                status=500,
            )

        if request.method == "HEAD" or status.get("status") == "preparing":
            response = Response({"status": "preparing"}, status=202)
            response["Retry-After"] = "5"
            return response

        redis = RedisArchivist()
        redis.set_message(
            playback_status_key(video_id),
            {"status": "preparing"},
            expire=300,
        )
        try:
            prepare_playback.delay(video_id, media_url)
        except Exception as error:  # pragma: no cover - broker boundary
            print(f"{video_id}: failed to queue playback: {error}")
            redis.set_message(
                playback_status_key(video_id),
                {
                    "status": "failed",
                    "error": "playback preparation could not be queued",
                },
                expire=300,
            )
            return Response(
                ErrorResponseSerializer(
                    {"error": "playback preparation could not be queued"}
                ).data,
                status=503,
            )

        response = Response({"status": "preparing"}, status=202)
        response["Retry-After"] = "5"
        return response

    def status(self, video_id: str):
        """Return playback state without triggering preparation."""
        media_url, _, error = self._get_media(video_id)
        if error:
            return error
        if media_url.lower().endswith(".mp4"):
            return Response({"status": "ready"})
        return Response(self._status_response(video_id))
