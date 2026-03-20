"""
Fork Feature: Audio Tracks – download hook

Implements the DownloadHook protocol from the fork registry.

Pre-download:
  - Determines whether multi-audio is requested for this video/channel.
  - Mutates the yt-dlp obs to select the correct format string.
  - Records HLS fallback formats that need a post-download merge.

Post-download:
  - Downloads temporary HLS fallback audio files.
  - Merges them into the main MP4 via ffmpeg.
  - Cleans up temporary files.
"""

from __future__ import annotations

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
        """Mutate *obs* for multi-audio and return context for post_download."""
        # We need a way to fetch available formats from yt-dlp.  Capture a
        # closure over config so we do not need the full VideoDownloader.
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

        hls_formats_to_merge: dict[str, str] = {}

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
                main_fmt = build_main_format(available_formats, dash_fmt)

                if main_fmt:
                    selected_audio_count = len(dash_fmt) + len(hls_fmt)
                    obs["format"] = main_fmt
                    if selected_audio_count > 1:
                        obs["audio_multistreams"] = True
                    print(f"{youtube_id}: main format: {main_fmt}")
                    hls_formats_to_merge = hls_fmt

                elif hls_fmt:
                    # No DASH video formats found; use first HLS as base.
                    first_lang, first_fmt = next(iter(hls_fmt.items()))
                    obs["format"] = first_fmt
                    print(
                        f"{youtube_id}: no DASH main format, using HLS "
                        f"{first_lang}:{first_fmt} as base"
                    )
                    hls_formats_to_merge = {
                        lang: fmt
                        for lang, fmt in hls_fmt.items()
                        if lang != first_lang
                    }

        return {
            "hls_formats_to_merge": hls_formats_to_merge,
            "config": config,
        }

    def post_download(
        self,
        context: dict[str, Any],
        youtube_id: str,
        dl_cache: str,
        success: bool,
    ) -> None:
        """Download HLS fallback tracks and merge them into the main MP4."""
        if not success:
            return

        hls_formats_to_merge: dict[str, str] = context.get(
            "hls_formats_to_merge", {}
        )
        if not hls_formats_to_merge:
            return

        config = context["config"]
        main_path = os.path.join(dl_cache, f"{youtube_id}.mp4")
        audio_tracks: list[tuple[str, str]] = []

        try:
            for lang, fmt_id in hls_formats_to_merge.items():
                track_path = self._download_hls_audio(
                    youtube_id, fmt_id, lang, dl_cache, config
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
    def _download_hls_audio(
        youtube_id: str,
        format_id: str,
        lang: str,
        dl_cache: str,
        config: dict[str, Any],
    ) -> str | None:
        """Download one HLS fallback variant to a temporary file."""
        base_name = f"{youtube_id}_audio_{lang}"
        hls_obs = {
            "format": format_id,
            "outtmpl": os.path.join(dl_cache, f"{base_name}.%(ext)s"),
            "audio_multistreams": False,
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        print(
            f"[audio_languages] downloading HLS fallback {lang}: {format_id}"
        )
        success, _ = YtWrap(hls_obs, config).download(youtube_id)
        if not success:
            print(
                f"[audio_languages] failed HLS fallback download for: {lang}"
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
        """Remove temporary fallback track files."""
        for _, track_path in audio_tracks:
            try:
                os.remove(track_path)
            except FileNotFoundError:
                pass
