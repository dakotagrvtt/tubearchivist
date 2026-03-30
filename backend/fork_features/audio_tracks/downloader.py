"""
Fork Feature: Audio Tracks – download hook

Implements the DownloadHook protocol from the fork registry.

Pre-download:
  - Determines whether multi-audio is requested for this video/channel.
  - Mutates the yt-dlp obs to select only the primary audio track in the
    format string (video + one audio).  All additional language tracks are
    staged for individual post-download.

Post-download:
  - Downloads each extra audio track individually (both leftover DASH and HLS
    fallback streams) so that multi-stream format strings are never passed to
    yt-dlp.  Relying on yt-dlp's built-in multi-stream merging is unreliable
    when a cookie is configured because yt-dlp's check_formats step sends
    individual HEAD requests to each stream URL; extra DASH audio URLs embed
    session tokens that fail this check, causing yt-dlp to silently drop the
    extra streams even on a nominally successful download.
  - Merges extra tracks into the main MP4 via ffmpeg.
  - Cleans up temporary files.
"""

from __future__ import annotations

import copy
import os
from typing import Any

from download.src.yt_dlp_base import YtWrap
from fork_features.audio_tracks.ffmpeg_merge import merge_additional_audio_tracks
from fork_features.audio_tracks.languages import (
    build_main_format,
    resolve_dash_audio_formats,
    resolve_hls_audio_formats,
    resolve_requested_audio_languages,
)


class AudioTracksDownloadHook:
    """DownloadHook that adds multi-language audio tracks to downloaded MP4s."""

    def pre_download(
        self,
        obs: dict[str, Any],
        youtube_id: str,
        channel_id: str,
        config: dict[str, Any],
        channel_overwrites: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Mutate *obs* for multi-audio and return context for post_download.

        Only the primary (first) DASH audio language is included in the main
        yt-dlp format string.  All additional DASH languages and any HLS
        fallback streams are collected into ``extra_audio_to_merge`` and
        downloaded individually in ``post_download``.  This avoids the
        ``check_formats: selected`` issue that causes yt-dlp to silently drop
        extra audio tracks when using a multi-stream format string.
        """
        def _get_formats(yt_id: str) -> list[dict]:
            extract_obs = {"skip_download": True, "quiet": True}
            yt_extract = YtWrap(extract_obs, config)
            response, error = yt_extract.extract(
                f"https://www.youtube.com/watch?v={yt_id}"
            )
            if not response or error:
                print(f"{yt_id}: failed to extract formats: {error}")
                return []
            return response.get("formats", [])

        languages, formats = resolve_requested_audio_languages(
            youtube_id, channel_id, config, channel_overwrites, _get_formats
        )

        extra_audio_to_merge: dict[str, str] = {}

        if languages:
            print(f"{youtube_id}: applying audio languages {languages}")
            available_formats = formats or _get_formats(youtube_id)

            if available_formats:
                dash_fmt = resolve_dash_audio_formats(
                    available_formats, languages
                )
                hls_fmt = resolve_hls_audio_formats(
                    available_formats, languages, dash_fmt
                )

                # Split DASH formats: use only the primary language in the
                # main format string; route the rest to individual downloads.
                if dash_fmt:
                    primary_lang = next(iter(dash_fmt))
                    primary_dash = {primary_lang: dash_fmt[primary_lang]}
                    extra_dash = {
                        lang: fmt_id
                        for lang, fmt_id in dash_fmt.items()
                        if lang != primary_lang
                    }
                else:
                    primary_dash = {}
                    extra_dash = {}

                main_fmt = build_main_format(available_formats, primary_dash)

                if main_fmt:
                    obs["format"] = main_fmt
                    # audio_multistreams is not needed: we only have one audio
                    # stream in the main format string.
                    print(f"{youtube_id}: main format: {main_fmt}")
                    # All extra DASH audio + HLS fallbacks are downloaded
                    # individually in post_download.
                    extra_audio_to_merge = {**extra_dash, **hls_fmt}

                elif hls_fmt:
                    # No DASH video-only streams found; use first HLS as base.
                    first_lang, first_fmt = next(iter(hls_fmt.items()))
                    obs["format"] = first_fmt
                    print(
                        f"{youtube_id}: no DASH main format, using HLS "
                        f"{first_lang}:{first_fmt} as base"
                    )
                    extra_audio_to_merge = {
                        **extra_dash,
                        **{
                            lang: fmt
                            for lang, fmt in hls_fmt.items()
                            if lang != first_lang
                        },
                    }

        multi_language = len(languages) > 1 if languages else False
        return {
            "extra_audio_to_merge": extra_audio_to_merge,
            "config": config,
            "multi_language": multi_language,
        }

    def post_download(
        self,
        context: dict[str, Any],
        youtube_id: str,
        dl_cache: str,
        success: bool,
    ) -> None:
        """Download extra audio tracks individually and merge into the MP4."""
        if not success:
            return

        extra_audio_to_merge: dict[str, str] = context.get(
            "extra_audio_to_merge", {}
        )
        if not extra_audio_to_merge:
            return

        config = context["config"]
        multi_language: bool = context.get("multi_language", False)
        main_path = os.path.join(dl_cache, f"{youtube_id}.mp4")
        audio_tracks: list[tuple[str, str]] = []

        try:
            for lang, fmt_id in extra_audio_to_merge.items():
                track_path = self._download_audio_track(
                    youtube_id, fmt_id, lang, dl_cache, config,
                    try_no_pot=multi_language,
                )
                if track_path:
                    audio_tracks.append((lang, track_path))

            if audio_tracks:
                merge_additional_audio_tracks(main_path, audio_tracks)
        finally:
            self._cleanup_audio_tracks(audio_tracks)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_pot_config(config: dict[str, Any]) -> dict[str, Any]:
        """Return a deep copy of config with pot_provider_url removed.

        Used when attempting an individual audio track download without the
        POT token.  POT may interfere with single DASH audio stream requests
        even when it works for the main video download.
        """
        no_pot = copy.deepcopy(config)
        no_pot["downloads"].pop("pot_provider_url", None)
        return no_pot

    @staticmethod
    def _download_audio_track(
        youtube_id: str,
        format_id: str,
        lang: str,
        dl_cache: str,
        config: dict[str, Any],
        try_no_pot: bool = False,
    ) -> str | None:
        """Download one extra audio track to a temporary file.

        Each extra language (both leftover DASH and HLS fallback) is
        downloaded as a separate single-stream request to avoid the
        multi-stream check_formats reliability issue.

        When *try_no_pot* is True the download is first attempted with cookie
        but without the POT token (POT can interfere with individual DASH
        audio stream requests).  If that fails the download is retried with
        the full config so age-restricted or private content can still be
        fetched.
        """
        base_name = f"{youtube_id}_audio_{lang}"
        track_obs = {
            "format": format_id,
            "outtmpl": os.path.join(dl_cache, f"{base_name}.%(ext)s"),
            "audio_multistreams": False,
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        print(
            f"[audio_languages] downloading extra audio {lang}: {format_id}"
        )

        if try_no_pot:
            # First attempt: cookie kept (required for authenticated DASH
            # format IDs) but POT stripped to avoid interference.
            print(
                f"[audio_languages] trying {lang} without POT first"
            )
            no_pot_config = AudioTracksDownloadHook._strip_pot_config(config)
            success, _ = YtWrap(track_obs, no_pot_config).download(youtube_id)
            if not success:
                print(
                    f"[audio_languages] no-POT attempt failed for {lang}, "
                    "retrying with full config"
                )
                success, _ = YtWrap(track_obs, config).download(youtube_id)
        else:
            success, _ = YtWrap(track_obs, config).download(youtube_id)

        if not success:
            print(
                f"[audio_languages] failed to download extra audio for: {lang}"
            )
            return None

        for fname in os.listdir(dl_cache):
            if fname.startswith(base_name + "."):
                return os.path.join(dl_cache, fname)

        return None

    @staticmethod
    def _cleanup_audio_tracks(
        audio_tracks: list[tuple[str, str]],
    ) -> None:
        """Remove temporary extra track files."""
        for _, track_path in audio_tracks:
            try:
                os.remove(track_path)
            except FileNotFoundError:
                pass
