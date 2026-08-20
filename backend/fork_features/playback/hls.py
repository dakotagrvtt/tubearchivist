"""On-demand HLS presentation for archived alternate audio tracks."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any

from appsettings.src.config import AppConfig
from celery import shared_task
from common.src.env_settings import EnvironmentSettings
from common.src.ta_redis import RedisArchivist
from fork_features.playback.media_paths import safe_path
from fork_features.playback.startup import cleanup_hls_cache
from fork_features.registry import is_feature_enabled

HLS_LOCK_TTL = 60 * 60
HLS_STATUS_TTL = 86400
RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


def hls_directory(video_id: str) -> str:
    return safe_path(
        os.path.join(EnvironmentSettings.CACHE_DIR, "hls"), video_id
    )


def hls_master_path(video_id: str) -> str:
    return safe_path(hls_directory(video_id), "master.m3u8")


def hls_asset_path(video_id: str, asset: str) -> str:
    return safe_path(hls_directory(video_id), asset)


def hls_status_key(video_id: str) -> str:
    return f"hls:{video_id}"


def hls_lock_key(video_id: str) -> str:
    return f"hls:{video_id}:lock"


def hls_cache_ready(video_id: str) -> bool:
    try:
        path = hls_master_path(video_id)
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except (OSError, ValueError):
        return False


def _language(stream: dict[str, Any], index: int) -> str:
    value = str(stream.get("language") or "und").strip()
    return re.sub(r"[^A-Za-z0-9_-]", "", value) or f"track{index + 1}"


def _name(stream: dict[str, Any], index: int) -> str:
    value = str(stream.get("title") or stream.get("language") or "")
    value = re.sub(r"[^A-Za-z0-9 _-]", "", value).strip()
    return value or f"Audio {index + 1}"


def _unique_names(names: list[str]) -> list[str]:
    """Keep original names while suffixing every later collision."""
    reserved = set(names)
    emitted: set[str] = set()
    next_suffix: dict[str, int] = {}
    unique_names = []

    for name in names:
        candidate = name
        if candidate in emitted:
            suffix = next_suffix.get(name, 1)
            while True:
                candidate = f"{name} {suffix}"
                suffix += 1
                if candidate not in reserved and candidate not in emitted:
                    break
            next_suffix[name] = suffix

        emitted.add(candidate)
        unique_names.append(candidate)

    return unique_names


def build_hls_command(
    source_path: str, output_dir: str, audio_streams: list[dict[str, Any]]
) -> list[str]:
    """Build one-quality HLS with alternate audio renditions."""
    command = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-i",
        source_path,
        "-map",
        "0:v:0",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-an",
        "-f",
        "hls",
        "-hls_time",
        "6",
        "-hls_playlist_type",
        "vod",
        "-hls_flags",
        "independent_segments",
        "-hls_segment_filename",
        os.path.join(output_dir, "video", "segment_%05d.ts"),
        os.path.join(output_dir, "video", "index.m3u8"),
    ]
    for index, stream in enumerate(audio_streams):
        command.extend(
            [
                "-map",
                f"0:{int(stream['index'])}",
                "-vn",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-f",
                "hls",
                "-hls_time",
                "6",
                "-hls_playlist_type",
                "vod",
                "-hls_flags",
                "independent_segments",
                "-hls_segment_filename",
                os.path.join(output_dir, f"audio{index}", "segment_%05d.ts"),
                os.path.join(output_dir, f"audio{index}", "index.m3u8"),
            ]
        )
    return command


def write_master_playlist(
    output_dir: str, audio_streams: list[dict[str, Any]]
) -> None:
    """Write one video rendition with alternate audio-only playlists."""
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-INDEPENDENT-SEGMENTS"]
    names = _unique_names(
        [_name(stream, index) for index, stream in enumerate(audio_streams)]
    )
    for index, stream in enumerate(audio_streams):
        default = "YES" if index == 0 else "NO"
        language = _language(stream, index)
        name = names[index].replace('"', "'")
        lines.append(
            '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",'
            f'LANGUAGE="{language}",NAME="{name}",'
            f'DEFAULT={default},AUTOSELECT=YES,URI="audio{index}/index.m3u8"'
        )
    lines.extend(
        [
            "#EXT-X-STREAM-INF:BANDWIDTH=1000000,AVERAGE-BANDWIDTH=800000,"
            'CODECS="avc1.64001f",AUDIO="audio"',
            "video/index.m3u8",
            "",
        ]
    )
    with open(
        os.path.join(output_dir, "master.m3u8"), "w", encoding="utf-8"
    ) as master:
        master.write("\n".join(lines))


def _set_status(redis: RedisArchivist, video_id: str, status: dict[str, Any]):
    redis.set_message(hls_status_key(video_id), status, expire=HLS_STATUS_TTL)


def _generate_hls_output(
    source_path: str,
    temporary_dir: str,
    audio_streams: list[dict[str, Any]],
) -> bool:
    """Build a complete temporary presentation ready for publication."""
    shutil.rmtree(temporary_dir, ignore_errors=True)
    os.makedirs(temporary_dir, exist_ok=True)
    os.makedirs(os.path.join(temporary_dir, "video"), exist_ok=True)
    for index in range(len(audio_streams)):
        os.makedirs(
            os.path.join(temporary_dir, f"audio{index}"), exist_ok=True
        )

    command = build_hls_command(source_path, temporary_dir, audio_streams)
    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    video_playlist = os.path.join(temporary_dir, "video", "index.m3u8")
    if result.returncode != 0 or not os.path.isfile(video_playlist):
        return False

    write_master_playlist(temporary_dir, audio_streams)
    return True


def _prepare_locked_hls(
    redis: RedisArchivist,
    video_id: str,
    media_url: str,
    audio_streams: list[dict[str, Any]],
) -> str:
    """Generate and publish HLS while the caller owns the worker lock."""
    output_dir = hls_directory(video_id)
    temporary_dir = f"{output_dir}.part"
    try:
        source_path = safe_path(EnvironmentSettings.MEDIA_DIR, media_url)
        if not os.path.isfile(source_path):
            _set_status(
                redis,
                video_id,
                {"status": "failed", "error": "video source is missing"},
            )
            return "failed"

        if hls_cache_ready(video_id):
            _set_status(redis, video_id, {"status": "ready"})
            return "ready"

        _set_status(redis, video_id, {"status": "preparing"})
        if not _generate_hls_output(source_path, temporary_dir, audio_streams):
            shutil.rmtree(temporary_dir, ignore_errors=True)
            _set_status(
                redis,
                video_id,
                {"status": "failed", "error": "HLS preparation failed"},
            )
            return "failed"

        shutil.rmtree(output_dir, ignore_errors=True)
        os.replace(temporary_dir, output_dir)
        cleanup_hls_cache()
        if not hls_cache_ready(video_id):
            _set_status(
                redis,
                video_id,
                {
                    "status": "failed",
                    "error": "HLS presentation exceeds the cache limit",
                },
            )
            return "failed"

        _set_status(redis, video_id, {"status": "ready"})
        return "ready"
    except (OSError, ValueError) as error:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        _set_status(redis, video_id, {"status": "failed", "error": str(error)})
        return "failed"


@shared_task(name="prepare_hls_playback")
def prepare_hls_playback(
    video_id: str, media_url: str, streams: list[dict[str, Any]]
) -> str:
    """Generate a reusable single-video-quality HLS presentation."""
    config = AppConfig().config
    if not is_feature_enabled(
        "multi_audio_playback", config
    ) or not is_feature_enabled("audio_tracks", config):
        try:
            RedisArchivist().del_message(hls_status_key(video_id))
        except Exception:  # pragma: no cover - Redis boundary
            pass
        return "disabled"

    audio_streams = [
        stream for stream in streams if stream.get("type") == "audio"
    ]
    if len(audio_streams) < 2:
        return "unavailable"

    redis = RedisArchivist()
    lock_key = redis.NAME_SPACE + hls_lock_key(video_id)
    token = os.urandom(24).hex()
    if not redis.conn.set(lock_key, token, nx=True, ex=HLS_LOCK_TTL):
        return "already-running"

    try:
        return _prepare_locked_hls(redis, video_id, media_url, audio_streams)
    finally:
        try:
            redis.conn.eval(RELEASE_LOCK_SCRIPT, 1, lock_key, token)
        except Exception:  # pragma: no cover - Redis boundary
            pass
