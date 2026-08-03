"""Runtime setup and cleanup owned by the playback feature."""

from __future__ import annotations

import os
from typing import Any

from common.src.env_settings import EnvironmentSettings


def ensure_cache_directory() -> None:
    """Create the persistent cache used for prepared playback media."""
    os.makedirs(
        os.path.join(EnvironmentSettings.CACHE_DIR, "transcode"),
        exist_ok=True,
    )


def clear_redis_state(redis: Any) -> int:
    """Clear request-scoped playback state after a process restart."""
    prefix = redis.NAME_SPACE + "playback:"
    removed = 0
    for key in redis.conn.scan_iter(match=prefix + "*"):
        removed += int(bool(redis.conn.delete(key)))
    return removed
