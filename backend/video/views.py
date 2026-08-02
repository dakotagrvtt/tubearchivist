"""all API views for video endpoints"""

import mimetypes
import os

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response

from common.serializers import ErrorResponseSerializer
from common.src.env_settings import EnvironmentSettings
from common.src.helper import calc_is_watched
from common.src.ta_redis import RedisArchivist
from common.src.watched import WatchState
from common.views_base import AdminWriteOnly, ApiBaseView
from playlist.src.index import YoutubePlaylist
from video.serializers import (
    CommentItemSerializer,
    PlayerSerializer,
    PlaylistNavItemSerializer,
    VideoListQuerySerializer,
    VideoListSerializer,
    VideoProgressUpdateSerializer,
    VideoSerializer,
)
from video.src.index import YoutubeVideo
from video.src.query_building import QueryBuilder
from video.tasks import (
    _safe_path,
    playback_cache_ready,
    playback_lock_key,
    playback_status_key,
    prepare_playback,
)


class VideoApiListView(ApiBaseView):
    """resolves to /api/video/
    GET: returns list of videos
    params:
    - playlist:str=<playlist-id>
    - channel:str=<channel-id>
    - watch:enum=watched|unwatched|continue
    - sort:enum=published|downloaded|views|likes|duration|filesize
    - order:enum=asc|desc
    - type:enum=videos|streams|shorts
    - height:int=px
    """

    search_base = "ta_video/_search/"

    @extend_schema(
        parameters=[VideoListQuerySerializer()],
        responses={
            200: VideoListSerializer(),
            400: OpenApiResponse(
                ErrorResponseSerializer(), description="bad request"
            ),
        },
    )
    def get(self, request):
        """get video list"""
        query_serializer = VideoListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        validated_query = query_serializer.validated_data

        data = QueryBuilder(request.user.id, **validated_query).build_data()
        if data == {"query": {"bool": {"must": [None]}}}:
            # skip empty lookup
            return Response([])

        self.data = data
        self.get_document_list(request, progress_match=request.user.id)

        response_serializer = VideoListSerializer(self.response)

        return Response(response_serializer.data)


class VideoApiView(ApiBaseView):
    """resolves to /api/video/<video_id>/
    GET: returns metadata dict of video
    """

    search_base = "ta_video/_doc/"
    permission_classes = [AdminWriteOnly]

    @extend_schema(
        responses={
            200: VideoSerializer(),
            404: OpenApiResponse(
                ErrorResponseSerializer(), description="video not found"
            ),
        },
    )
    def get(self, request, video_id):
        """get video"""
        self.get_document(video_id, progress_match=request.user.id)
        if not self.response:
            error = ErrorResponseSerializer({"error": "video not found"})
            return Response(error.data, status=404)

        serializer = VideoSerializer(self.response)
        return Response(serializer.data)

    @extend_schema(
        responses={
            204: OpenApiResponse(description="video deleted"),
            404: OpenApiResponse(
                ErrorResponseSerializer(), description="video not found"
            ),
        }
    )
    def delete(self, request, video_id):
        # pylint: disable=unused-argument
        """delete video"""
        try:
            YoutubeVideo(video_id).delete_media_file()
        except FileNotFoundError:
            error = ErrorResponseSerializer({"error": "video not found"})
            return Response(error.data, status=404)

        return Response(status=204)


class VideoCommentView(ApiBaseView):
    """resolves to /api/video/<video_id>/comment/
    handle video comments
    GET: return all comments from video with reply threads
    """

    search_base = "ta_comment/_doc/"

    @extend_schema(
        responses={
            200: CommentItemSerializer(),
            404: OpenApiResponse(
                ErrorResponseSerializer(), description="video not found"
            ),
        }
    )
    def get(self, request, video_id):
        """get video comments"""
        # pylint: disable=unused-argument
        self.get_document(video_id)
        if self.status_code == 404:
            error = ErrorResponseSerializer({"error": "video not found"})
            return Response(error.data, status=404)

        serializer = CommentItemSerializer(self.response, many=True)

        return Response(serializer.data)


class VideoApiNavView(ApiBaseView):
    """resolves to /api/video/<video-id>/nav/
    GET: returns playlist nav
    """

    search_base = "ta_video/_doc/"

    @extend_schema(
        responses={
            200: PlaylistNavItemSerializer(),
            404: OpenApiResponse(
                ErrorResponseSerializer(), description="video not found"
            ),
        }
    )
    def get(self, request, video_id):
        # pylint: disable=unused-argument
        """get video playlist nav"""
        self.get_document(video_id)
        if self.status_code == 404:
            error = ErrorResponseSerializer({"error": "video not found"})
            return Response(error.data, status=404)

        playlist_nav = []

        if not self.response.get("playlist"):
            return Response(playlist_nav)

        for playlist_id in self.response["playlist"]:
            playlist = YoutubePlaylist(playlist_id)
            playlist.get_from_es()
            playlist.build_nav(video_id)
            if playlist.nav:
                playlist_nav.append(playlist.nav)

        response_serializer = PlaylistNavItemSerializer(
            playlist_nav, many=True
        )

        return Response(response_serializer.data)


class VideoProgressView(ApiBaseView):
    """resolves to /api/video/<video_id>/progress/
    handle progress status for video
    """

    search_base = "ta_video/_doc/"

    @staticmethod
    def _get_key(user_id: int, video_id: str) -> str:
        """redis key"""
        return f"{user_id}:progress:{video_id}"

    @extend_schema(
        request=VideoProgressUpdateSerializer(),
        responses={
            200: PlayerSerializer(),
            404: OpenApiResponse(
                ErrorResponseSerializer(), description="video not found"
            ),
        },
    )
    def post(self, request, video_id):
        """set video progress position in redis"""
        data_serializer = VideoProgressUpdateSerializer(data=request.data)
        data_serializer.is_valid(raise_exception=True)
        validated_data = data_serializer.validated_data

        self.get_document(video_id)
        if self.status_code == 404:
            error = ErrorResponseSerializer({"error": "video not found"})
            return Response(error.data, status=404)

        position = validated_data["position"]
        key = self._get_key(request.user.id, video_id)
        redis_con = RedisArchivist()
        current_progress = (
            redis_con.get_message_dict(key) or self.response["player"]
        )

        current_progress.update({"position": position, "youtube_id": video_id})
        watched = self._check_watched(request, video_id, current_progress)
        if watched:
            expire = 60
        else:
            expire = False

        current_progress.update({"watched": watched})
        if position > 5:
            redis_con.set_message(key, current_progress, expire=expire)

        response_serializer = PlayerSerializer(current_progress)

        return Response(response_serializer.data)

    def _check_watched(self, request, video_id, current_progress) -> bool:
        """check watched state"""
        if current_progress["watched"]:
            return True

        watched = calc_is_watched(
            current_progress["duration"], current_progress["position"]
        )
        if watched:
            WatchState(video_id, watched, request.user.id).change()

        return watched

    @extend_schema(
        responses={
            204: OpenApiResponse(description="video progress deleted"),
        }
    )
    def delete(self, request, video_id):
        """delete progress position"""
        key = self._get_key(request.user.id, video_id)
        RedisArchivist().del_message(key)

        return Response(status=204)


class VideoSimilarView(ApiBaseView):
    """resolves to /api/video/<video-id>/similar/
    GET: return max 6 videos similar to this
    """

    search_base = "ta_video/_search/"

    @extend_schema(
        responses=VideoSerializer(many=True),
    )
    def get(self, request, video_id):
        """get similar videos"""
        self.data = {
            "size": 6,
            "query": {
                "more_like_this": {
                    "fields": ["tags", "title"],
                    "like": {"_id": video_id},
                    "min_term_freq": 1,
                    "max_query_terms": 25,
                }
            },
        }
        self.get_document_list(request, pagination=False)
        serializer = VideoSerializer(self.response["data"], many=True)
        return Response(serializer.data)


class VideoStreamView(ApiBaseView):
    """resolves to /api/video/<video_id>/stream/
    GET: return mp4 stream for playback
    """

    search_base = "ta_video/_doc/"

    def _get_media(self, video_id):
        """Return the indexed media URL and safe source path."""
        self.get_document(video_id)
        if self.status_code == 404 or not isinstance(self.response, dict):
            return None, None, Response(
                ErrorResponseSerializer({"error": "video not found"}).data,
                status=404,
            )

        media_url = self.response.get("media_url")
        if not media_url:
            return None, None, Response(
                ErrorResponseSerializer({"error": "video missing"}).data,
                status=404,
            )

        # SearchProcess exposes media URLs with the web root prefix (for
        # example ``/youtube/channel/id.mp4``), while storage helpers expect a
        # path relative to MEDIA_DIR. Normalize both forms before validation
        # and before constructing an internal Nginx redirect.
        media_url = str(media_url).lstrip("/")
        media_root = EnvironmentSettings.MEDIA_DIR.strip("/")
        if media_root and media_url.startswith(media_root + "/"):
            media_url = media_url[len(media_root) + 1 :]

        try:
            media_path = _safe_path(EnvironmentSettings.MEDIA_DIR, media_url)
        except ValueError:
            media_path = None
        if not media_path or not os.path.isfile(media_path):
            return None, None, Response(
                ErrorResponseSerializer({"error": "video missing"}).data,
                status=404,
            )
        return media_url, media_path, None

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

    @extend_schema(
        responses={
            200: OpenApiResponse(description="video stream"),
            202: OpenApiResponse(description="playback preparation queued"),
            404: OpenApiResponse(
                ErrorResponseSerializer(), description="video not found"
            ),
        },
    )
    def get(self, request, video_id):
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

        # HEAD is used by the player as a cheap poll and must not enqueue work.
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
            print(f"{video_id}: failed to queue playback preparation: {error}")
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


class VideoPlaybackStatusView(VideoStreamView):
    """Return playback preparation state without triggering preparation."""

    def get(self, request, video_id):  # pylint: disable=unused-argument
        media_url, _, error = self._get_media(video_id)
        if error:
            return error
        if media_url.lower().endswith(".mp4"):
            return Response({"status": "ready"})
        return Response(self._status_response(video_id))
