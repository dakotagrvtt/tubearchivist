"""Language and format selection helpers for the multi-audio feature."""

from __future__ import annotations

import re
from typing import Any, Callable

from yt_dlp.utils import ISO639Utils

_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$")


def is_audio_multistream_enabled(
    channel_id: str,
    config: dict[str, Any],
    channel_overwrites: dict[str, dict[str, Any]],
) -> bool:
    """Resolve the channel override before the global setting."""
    overwrites = channel_overwrites.get(channel_id, {})
    value = overwrites.get("audio_multistreams")
    if value is not None:
        return bool(value)
    return bool(config.get("downloads", {}).get("audio_multistreams"))


def normalize_requested_languages(value: Any) -> list[str]:
    """Normalize a comma-separated BCP-47 value and remove duplicates."""
    if not isinstance(value, str):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for raw in value.split(","):
        language = raw.strip().replace("_", "-")
        if not language or not _LANGUAGE_RE.fullmatch(language):
            continue
        parts = language.split("-")
        normalized = "-".join([parts[0].lower(), *parts[1:]])
        if normalized.casefold() not in seen:
            seen.add(normalized.casefold())
            result.append(normalized)
    return result


def get_audio_languages(
    channel_id: str,
    config: dict[str, Any],
    channel_overwrites: dict[str, dict[str, Any]],
) -> list[str] | None:
    """Return configured languages only when the feature is enabled."""
    if not is_audio_multistream_enabled(
        channel_id, config, channel_overwrites
    ):
        return None

    overwrites = channel_overwrites.get(channel_id, {})
    value = overwrites.get("audio_languages")
    if value is None:
        value = config.get("downloads", {}).get("audio_languages")
    languages = normalize_requested_languages(value)
    return languages or None


def _language_matches(candidate: Any, requested: str) -> bool:
    if not isinstance(candidate, str):
        return False
    candidate = candidate.strip().replace("_", "-").casefold()
    requested = requested.casefold()
    return (
        candidate == requested
        or candidate.startswith(requested + "-")
        or requested.startswith(candidate + "-")
    )


def _format_bitrate(fmt: dict) -> float:
    """Read yt-dlp's bitrate value without trusting its serialized type."""
    try:
        return float(fmt.get("tbr") or 0)
    except (TypeError, ValueError):
        return 0


def discover_audio_languages(formats: list[dict]) -> list[str]:
    """Collect unique, valid language tags from audio-capable formats."""
    result: list[str] = []
    seen: set[str] = set()
    for fmt in formats:
        if (fmt.get("acodec") or "none") == "none":
            continue
        languages = normalize_requested_languages(fmt.get("language"))
        for language in languages:
            if language.casefold() not in seen:
                seen.add(language.casefold())
                result.append(language)
    return result


def resolve_requested_audio_languages(
    youtube_id: str,
    channel_id: str,
    config: dict[str, Any],
    channel_overwrites: dict[str, dict[str, Any]],
    get_formats_fn: Callable[[str], list[dict]],
) -> tuple[list[str] | None, list[dict] | None]:
    """Resolve explicit languages or discover all available languages."""
    languages = get_audio_languages(channel_id, config, channel_overwrites)
    if languages:
        return languages, None
    if not is_audio_multistream_enabled(
        channel_id, config, channel_overwrites
    ):
        return None, None

    print(f"{youtube_id}: auto-discovering audio languages")
    formats = get_formats_fn(youtube_id)
    if not formats:
        return None, formats
    languages = discover_audio_languages(formats)
    return languages or None, formats


def resolve_dash_audio_formats(
    formats: list[dict], languages: list[str]
) -> dict[str, str]:
    """Choose the highest bitrate direct audio format for each language."""
    selected: dict[str, str] = {}
    for language in languages:
        candidates = [
            fmt
            for fmt in formats
            if (fmt.get("vcodec") or "none") == "none"
            and (fmt.get("acodec") or "none") != "none"
            and _language_matches(fmt.get("language"), language)
            and fmt.get("protocol") in ("https", "http")
            and fmt.get("format_id")
        ]
        if not candidates:
            continue
        chosen = max(candidates, key=_format_bitrate)
        selected[language] = chosen["format_id"]
    return selected


def resolve_hls_audio_formats(
    formats: list[dict],
    languages: list[str],
    dash_formats: dict[str, str],
) -> dict[str, str]:
    """Choose a muxed HLS fallback for languages without DASH audio."""
    selected: dict[str, str] = {}
    for language in languages:
        if language in dash_formats:
            continue
        candidates = [
            fmt
            for fmt in formats
            if (fmt.get("acodec") or "none") != "none"
            and _language_matches(fmt.get("language"), language)
            and "m3u8" in (fmt.get("protocol") or "")
            and fmt.get("format_id")
        ]
        if candidates:
            chosen = min(candidates, key=_format_bitrate)
            selected[language] = chosen["format_id"]
    return selected


def normalize_language_code(language: str) -> str:
    """Return an ISO-639-2 code suitable for container metadata."""
    primary = (language or "").replace("_", "-").split("-")[0].strip().lower()
    if len(primary) == 2:
        converted = ISO639Utils.short2long(primary)
        return converted if converted and len(converted) == 3 else "und"
    return primary if len(primary) == 3 else "und"


def language_title(language: str) -> str:
    """Return a readable title for a track."""
    code = normalize_language_code(language)
    long_name = ISO639Utils.short2long(code)
    return long_name or (language.upper() if language else "Unknown")
