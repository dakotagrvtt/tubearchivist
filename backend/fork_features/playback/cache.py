"""Playback cache lifecycle helpers."""

from __future__ import annotations

import os

from common.src.ta_redis import RedisArchivist
from fork_features.playback.hls import hls_directory, hls_status_key
from fork_features.playback.tasks import (
    playback_cache_path,
    playback_status_key,
)


def invalidate_playback_cache(video_id: str) -> None:
    """Discard prepared media and state after replacing source media."""
    cache_path = playback_cache_path(video_id)
    for stale_path in (
        cache_path,
        f"{cache_path}.part",
        f"{cache_path}.part.mp4",
    ):
        try:
            os.remove(stale_path)
        except FileNotFoundError:
            pass
        except OSError as error:
            print(f"{video_id}: failed to remove playback cache: {error}")

    try:
        import shutil

        shutil.rmtree(hls_directory(video_id), ignore_errors=True)
        shutil.rmtree(f"{hls_directory(video_id)}.part", ignore_errors=True)
    except (OSError, ValueError) as error:
        print(f"{video_id}: failed to remove HLS cache: {error}")

    try:
        redis = RedisArchivist()
        redis.del_message(playback_status_key(video_id))
        redis.del_message(hls_status_key(video_id))
    except Exception as error:  # pragma: no cover - Redis boundary
        print(f"{video_id}: failed to clear playback status: {error}")
