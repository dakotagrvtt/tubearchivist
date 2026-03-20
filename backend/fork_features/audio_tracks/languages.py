"""
Fork Feature: Audio Tracks – language resolution helpers

Handles:
- Deciding whether multi-audio is enabled (global or per-channel overwrite)
- Resolving explicit or auto-discovered language lists
- Mapping two-letter ISO codes to three-letter codes for ffmpeg metadata
- Selecting the best DASH and HLS audio format IDs per language
"""

from __future__ import annotations

from typing import Any

from yt_dlp.utils import ISO639Utils


# ---------------------------------------------------------------------------
# Enabled / language list resolution
# ---------------------------------------------------------------------------


def is_audio_multistream_enabled(
    channel_id: str,
    config: dict[str, Any],
    channel_overwrites: dict[str, dict[str, Any]],
) -> bool:
    """Return True when audio_multistreams is effectively enabled."""
    overwrites = channel_overwrites.get(channel_id, {})
    if (
        "audio_multistreams" in overwrites
        and overwrites["audio_multistreams"] is not None
    ):
        return bool(overwrites["audio_multistreams"])
    return bool(config["downloads"].get("audio_multistreams"))


def get_audio_languages(
    channel_id: str,
    config: dict[str, Any],
    channel_overwrites: dict[str, dict[str, Any]],
) -> list[str] | None:
    """Return configured audio languages, or None if multistream is off.

    ``audio_languages`` alone does not force multi-track downloads; the
    ``audio_multistreams`` flag must also be enabled.
    """
    if not is_audio_multistream_enabled(channel_id, config, channel_overwrites):
        return None

    overwrites = channel_overwrites.get(channel_id, {})
    audio_languages = overwrites.get(
        "audio_languages",
        config["downloads"].get("audio_languages"),
    )
    if not audio_languages:
        return None

    return [
        lang.strip() for lang in audio_languages.split(",") if lang.strip()
    ]


def discover_audio_languages(formats: list[dict]) -> list[str]:
    """Collect all unique audio language codes available in *formats*."""
    seen: set[str] = set()
    langs: list[str] = []
    for f in formats:
        if (f.get("acodec") or "none") == "none":
            continue
        lang = (f.get("language") or "").strip()
        if lang and lang not in seen:
            seen.add(lang)
            langs.append(lang)
    return langs


def resolve_requested_audio_languages(
    youtube_id: str,
    channel_id: str,
    config: dict[str, Any],
    channel_overwrites: dict[str, dict[str, Any]],
    get_formats_fn,
) -> tuple[list[str] | None, list[dict] | None]:
    """Return the final language list (and available formats) for a video.

    Tries explicit settings first; falls back to auto-discovery when
    ``audio_multistreams`` is on but no explicit languages are configured.
    *get_formats_fn* is a callable ``(youtube_id) -> list[dict]``.
    """
    languages = get_audio_languages(channel_id, config, channel_overwrites)
    if languages:
        return languages, None

    if not is_audio_multistream_enabled(channel_id, config, channel_overwrites):
        return None, None

    print(
        f"{youtube_id}: audio_multistreams enabled, auto-discovering languages"
    )
    formats = get_formats_fn(youtube_id)
    if not formats:
        return None, formats

    languages = discover_audio_languages(formats)
    print(f"{youtube_id}: discovered audio languages: {languages}")
    return languages, formats


# ---------------------------------------------------------------------------
# Format selection (DASH / HLS)
# ---------------------------------------------------------------------------


def resolve_dash_audio_formats(
    formats: list[dict], languages: list[str]
) -> dict[str, str]:
    """Pick one DASH audio-only format per requested language.

    Returns a mapping of language-code → format_id.
    """
    dash_formats: dict[str, str] = {}

    for lang in languages:
        dash = [
            f
            for f in formats
            if (f.get("vcodec") or "none") == "none"
            and (f.get("acodec") or "none") != "none"
            and (f.get("language") or "").startswith(lang)
            and f.get("protocol") in ("https", "http")
        ]
        if dash:
            dash.sort(key=lambda f: f.get("tbr") or 0, reverse=True)
            chosen = dash[0]
            dash_formats[lang] = chosen["format_id"]
            print(
                f"[audio_languages] {lang}: DASH audio "
                f"{chosen['format_id']} ({chosen.get('acodec')}, "
                f"{chosen.get('tbr')}kbps)"
            )
            continue

        print(f"[audio_languages] no DASH audio found for: {lang}")

    return dash_formats


def resolve_hls_audio_formats(
    formats: list[dict],
    languages: list[str],
    dash_formats: dict[str, str],
) -> dict[str, str]:
    """Pick one HLS muxed fallback format for languages missing DASH.

    Some uploads expose extra languages only via HLS muxed variants.
    DASH is preferred; this builds a fallback list for the remainder.
    """
    hls_formats: dict[str, str] = {}

    for lang in languages:
        if lang in dash_formats:
            continue

        hls = [
            f
            for f in formats
            if (f.get("acodec") or "none") != "none"
            and (f.get("language") or "").startswith(lang)
            and "m3u8" in (f.get("protocol") or "")
        ]
        if not hls:
            continue

        hls.sort(key=lambda f: f.get("tbr") or 0)
        chosen = hls[0]
        hls_formats[lang] = chosen["format_id"]
        print(
            f"[audio_languages] {lang}: HLS fallback "
            f"{chosen['format_id']} ({chosen.get('acodec')}, "
            f"{chosen.get('tbr')}kbps)"
        )

    return hls_formats


def build_main_format(
    formats: list[dict], dash_lang_formats: dict[str, str]
) -> str | None:
    """Build the yt-dlp ``--format`` string for DASH video + audio tracks."""
    video_only = [
        f
        for f in formats
        if (f.get("vcodec") or "none") != "none"
        and (f.get("acodec") or "none") == "none"
    ]
    if not video_only:
        print("[audio_languages] no video-only formats found")
        return None

    video_only.sort(
        key=lambda f: (f.get("height") or 0, f.get("tbr") or 0),
        reverse=True,
    )
    best_video = video_only[0]
    print(
        f"[audio_languages] best video: {best_video['format_id']} "
        f"({best_video.get('height')}p, {best_video.get('vcodec')})"
    )

    if not dash_lang_formats:
        return None

    parts = [best_video["format_id"]] + list(dash_lang_formats.values())
    format_str = "+".join(parts)
    print(f"[audio_languages] main format string: {format_str}")
    return format_str


# ---------------------------------------------------------------------------
# Language code utilities
# ---------------------------------------------------------------------------


def normalize_language_code(lang: str) -> str:
    """Best-effort normalisation to ISO-639-2/T three-letter codes for ffmpeg."""
    if not lang:
        return "und"

    primary = lang.split("-")[0].strip().lower()
    if not primary:
        return "und"

    if len(primary) == 2:
        converted = ISO639Utils.short2long(primary)
        if converted and len(converted) == 3:
            return converted
        return "und"

    if len(primary) == 3:
        return primary

    return primary


def language_title(lang: str) -> str:
    """Build a human-friendly stream title from a language tag."""
    if not lang:
        return "Unknown"

    code = normalize_language_code(lang)
    long_name = ISO639Utils.short2long(code)
    if long_name:
        return long_name

    return lang.upper()
