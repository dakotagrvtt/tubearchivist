"""Background preparation for browser-compatible video playback."""

from __future__ import annotations

import os
import secrets
import subprocess

from celery import shared_task
from common.src.env_settings import EnvironmentSettings
from common.src.ta_redis import RedisArchivist
from fork_features.playback.media_paths import safe_path

PLAYBACK_LOCK_TTL = 60 * 60
PLAYBACK_LOCK_RENEW_INTERVAL = 5 * 60
RENEW_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
end
return 0
"""
RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


def playback_cache_path(video_id: str) -> str:
    """Return the deterministic browser-playback cache path."""
    return safe_path(
        os.path.join(EnvironmentSettings.CACHE_DIR, "transcode"),
        f"{video_id}.mp4",
    )


def playback_status_key(video_id: str) -> str:
    return f"playback:{video_id}"


def playback_lock_key(video_id: str) -> str:
    return f"playback:{video_id}:lock"


def playback_cache_ready(video_id: str) -> bool:
    """Return whether a completed playback artifact is usable."""
    try:
        path = playback_cache_path(video_id)
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def _remove_file(path: str) -> None:
    """Remove a temporary artifact when it exists."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _source_changed(path: str, original_stat: os.stat_result) -> bool:
    """Detect a source replacement while ffmpeg was running."""
    try:
        current_stat = os.stat(path)
    except FileNotFoundError:
        return True

    return (
        current_stat.st_mtime_ns != original_stat.st_mtime_ns
        or current_stat.st_size != original_stat.st_size
        or current_stat.st_ino != original_stat.st_ino
    )


def _output_ready(path: str) -> bool:
    """Return whether ffmpeg produced a non-empty temporary artifact."""
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def _renew_playback_lock(
    redis: RedisArchivist,
    lock_key: str,
    status_key: str,
    lock_token: str,
) -> bool:
    """Renew the lease only while this worker still owns it."""
    try:
        renewed = bool(
            redis.conn.eval(
                RENEW_LOCK_SCRIPT,
                1,
                lock_key,
                lock_token,
                PLAYBACK_LOCK_TTL,
            )
        )
    except Exception:  # pragma: no cover - redis connection boundary
        return False

    if renewed:
        try:
            redis.set_message(
                status_key,
                {"status": "preparing"},
                expire=PLAYBACK_LOCK_TTL,
            )
        except Exception:  # pragma: no cover - redis connection boundary
            pass

    return renewed


def _release_playback_lock(
    redis: RedisArchivist, lock_key: str, lock_token: str
) -> None:
    """Release only the lease acquired by this worker."""
    try:
        redis.conn.eval(
            RELEASE_LOCK_SCRIPT,
            1,
            lock_key,
            lock_token,
        )
    except Exception:  # pragma: no cover - redis connection boundary
        pass


def _stop_process(process: subprocess.Popen) -> None:
    """Stop an ffmpeg process after losing its coordination lease."""
    if process.poll() is not None:
        return

    try:
        process.terminate()
    except ProcessLookupError:
        return

    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            return
        process.wait()


def _run_ffmpeg_with_lease(
    command: list[str],
    redis: RedisArchivist,
    lock_key: str,
    status_key: str,
    lock_token: str,
) -> tuple[int, bool]:
    """Run ffmpeg while renewing its Redis lease."""
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    while True:
        try:
            return process.wait(timeout=PLAYBACK_LOCK_RENEW_INTERVAL), True
        except subprocess.TimeoutExpired:
            if not _renew_playback_lock(
                redis, lock_key, status_key, lock_token
            ):
                _stop_process(process)
                return process.returncode or -1, False


@shared_task(name="prepare_playback")
def prepare_playback(video_id: str, media_url: str) -> str:
    """Transcode one source file once, outside the request process."""
    redis = RedisArchivist()
    lock_key = redis.NAME_SPACE + playback_lock_key(video_id)
    status_key = playback_status_key(video_id)
    cache_dir = os.path.join(EnvironmentSettings.CACHE_DIR, "transcode")
    cache_path = playback_cache_path(video_id)

    if playback_cache_ready(video_id):
        redis.set_message(status_key, {"status": "ready"}, expire=86400)
        return "ready"

    lock_token = secrets.token_urlsafe(32)
    if not redis.conn.set(lock_key, lock_token, nx=True, ex=PLAYBACK_LOCK_TTL):
        return "already-running"

    temporary_path: str | None = None
    try:
        source_path = safe_path(EnvironmentSettings.MEDIA_DIR, media_url)
        if not os.path.isfile(source_path):
            redis.set_message(
                status_key,
                {"status": "failed", "error": "video source is missing"},
                expire=300,
            )
            return "failed"
        source_stat = os.stat(source_path)

        os.makedirs(cache_dir, exist_ok=True)
        temporary_path = f"{cache_path}.part.mp4"
        _remove_file(temporary_path)

        redis.set_message(
            status_key,
            {"status": "preparing"},
            expire=PLAYBACK_LOCK_TTL,
        )
        command = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-i",
            source_path,
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            temporary_path,
        ]
        return_code, lease_owned = _run_ffmpeg_with_lease(
            command,
            redis,
            lock_key,
            status_key,
            lock_token,
        )
        if not lease_owned or not _renew_playback_lock(
            redis, lock_key, status_key, lock_token
        ):
            _remove_file(temporary_path)
            return "lock-lost"
        if _source_changed(source_path, source_stat):
            _remove_file(temporary_path)
            redis.set_message(status_key, {"status": "pending"}, expire=60)
            return "stale-source"
        if return_code != 0 or not _output_ready(temporary_path):
            _remove_file(temporary_path)
            redis.set_message(
                status_key,
                {
                    "status": "failed",
                    "error": "ffmpeg playback preparation failed",
                },
                expire=300,
            )
            return "failed"

        os.replace(temporary_path, cache_path)
        redis.set_message(status_key, {"status": "ready"}, expire=86400)
        return "ready"
    except (OSError, ValueError) as error:
        if temporary_path:
            _remove_file(temporary_path)
        redis.set_message(
            status_key,
            {"status": "failed", "error": str(error)},
            expire=300,
        )
        return "failed"
    finally:
        _release_playback_lock(redis, lock_key, lock_token)
