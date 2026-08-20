"""Runtime setup and cleanup owned by the playback feature."""

from __future__ import annotations

import os
import shutil
import time
from typing import Any

from common.src.env_settings import EnvironmentSettings

HLS_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
HLS_MAX_BYTES = 10 * 1024 * 1024 * 1024


def ensure_cache_directory() -> None:
    """Create the persistent cache used for prepared playback media."""
    os.makedirs(
        os.path.join(EnvironmentSettings.CACHE_DIR, "transcode"),
        exist_ok=True,
    )
    os.makedirs(
        os.path.join(EnvironmentSettings.CACHE_DIR, "hls"),
        exist_ok=True,
    )
    cleanup_hls_cache()


def cleanup_hls_cache(
    max_age_seconds: int = HLS_MAX_AGE_SECONDS,
    max_bytes: int = HLS_MAX_BYTES,
) -> int:
    """Reclaim old or oversized generated HLS presentations."""
    root = os.path.join(EnvironmentSettings.CACHE_DIR, "hls")
    if not os.path.isdir(root):
        return 0

    now = time.time()
    entries: list[tuple[float, int, str]] = []
    removed = 0
    for name in os.listdir(root):
        path = os.path.join(root, name)
        try:
            modified = os.path.getmtime(path)
            size = sum(
                os.path.getsize(os.path.join(directory, filename))
                for directory, _, filenames in os.walk(path)
                for filename in filenames
            )
        except OSError:
            continue
        if now - modified > max_age_seconds:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
            continue
        entries.append((modified, size, path))

    total = sum(size for _, size, _ in entries)
    for modified, size, path in sorted(entries):
        if total <= max_bytes:
            break
        shutil.rmtree(path, ignore_errors=True)
        total -= size
        removed += 1

    return removed


def clear_redis_state(redis: Any) -> int:
    """Clear request-scoped playback state after a process restart."""
    removed = 0
    for prefix in ("playback:", "hls:"):
        namespaced = redis.NAME_SPACE + prefix
        for key in redis.conn.scan_iter(match=namespaced + "*"):
            removed += int(bool(redis.conn.delete(key)))
    return removed
