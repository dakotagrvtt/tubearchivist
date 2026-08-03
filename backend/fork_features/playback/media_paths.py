"""Safe archive and playback-cache path resolution."""

from __future__ import annotations

import os
import urllib.parse

from common.src.env_settings import EnvironmentSettings

ARCHIVE_MEDIA_EXTENSIONS = (
    ".mp4",
    ".mkv",
    ".webm",
    ".mov",
    ".m4v",
    ".ts",
    ".avi",
    ".flv",
)


def safe_path(root: str, relative: str) -> str:
    """Resolve a relative path and reject traversal outside ``root``."""
    root_path = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_path, relative))
    if os.path.commonpath((root_path, candidate)) != root_path:
        raise ValueError("media path escapes configured storage")
    return candidate


def normalize_media_url(media_url: str) -> str:
    """Convert a processed web media URL back to an archive-relative path."""
    normalized = urllib.parse.unquote(str(media_url)).lstrip("/")
    media_root = EnvironmentSettings.MEDIA_DIR.strip("/")
    if media_root and normalized.startswith(media_root + "/"):
        normalized = normalized[len(media_root) + 1 :]  # noqa: E203

    return normalized


def resolve_archived_media_path(
    media_url: str, video_id: str
) -> tuple[str, str] | None:
    """Resolve an indexed media URL, including a safe extension fallback."""
    normalized = normalize_media_url(media_url)
    try:
        indexed_path = safe_path(EnvironmentSettings.MEDIA_DIR, normalized)
    except ValueError:
        return None

    if os.path.isfile(indexed_path):
        return normalized, indexed_path

    media_dir = os.path.dirname(normalized)
    for extension in ARCHIVE_MEDIA_EXTENSIONS:
        candidate_url = os.path.join(media_dir, video_id + extension)
        if candidate_url == normalized:
            continue
        try:
            candidate_path = safe_path(
                EnvironmentSettings.MEDIA_DIR, candidate_url
            )
        except ValueError:
            continue
        if os.path.isfile(candidate_path):
            return candidate_url, candidate_path

    return None
