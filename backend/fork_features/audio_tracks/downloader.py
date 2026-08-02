"""Download hook for optional language tracks.

The primary download always uses TubeArchivist's effective yt-dlp options.
The feature only discovers and stages additional tracks; it must not silently
replace a user's format or container selection with a guessed one.
"""

from __future__ import annotations

import copy
import os
import shutil
import tempfile
from typing import Any

from download.src.yt_dlp_base import YtWrap
from fork_features.audio_tracks.ffmpeg_merge import (
    merge_additional_audio_tracks,
)
from fork_features.audio_tracks.languages import (
    resolve_dash_audio_formats,
    resolve_hls_audio_formats,
    resolve_requested_audio_languages,
)


class AudioTracksDownloadHook:
    """Stage extra audio tracks and merge them after a successful download."""

    def pre_download(
        self,
        obs: dict[str, Any],
        youtube_id: str,
        channel_id: str,
        config: dict[str, Any],
        channel_overwrites: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        def get_formats(video_id: str) -> list[dict]:
            extract_obs = {"skip_download": True, "quiet": True}
            response, error = YtWrap(extract_obs, config).extract(
                f"https://www.youtube.com/watch?v={video_id}"
            )
            if not response or error:
                print(f"{video_id}: failed to extract audio formats: {error}")
                return []
            return response.get("formats", [])

        languages, formats = resolve_requested_audio_languages(
            youtube_id,
            channel_id,
            config,
            channel_overwrites,
            get_formats,
        )
        if not languages:
            return {}

        available = formats or get_formats(youtube_id)
        # Explicitly configured languages are valid even when only one was
        # requested. Auto-discovery of a single language adds no value because
        # it is already the primary stream selected by yt-dlp.
        if not available or (formats is not None and len(languages) < 2):
            return {}

        # Keep the effective primary format untouched, then archive every
        # requested/discovered language separately.  If the primary format
        # already contains one of these languages, the duplicate is harmless
        # and the browser still deterministically starts with stream zero.
        extra_languages = languages
        dash = resolve_dash_audio_formats(available, extra_languages)
        hls = resolve_hls_audio_formats(available, extra_languages, dash)
        extra_formats = {**dash, **hls}
        if not extra_formats:
            return {}

        cache_dir = os.path.dirname(
            str(obs.get("outtmpl", os.path.join("/tmp", "%(id)s.mp4")))
        ) or os.getcwd()
        os.makedirs(cache_dir, exist_ok=True)
        temp_dir = tempfile.mkdtemp(prefix=f"ta-audio-{youtube_id}-")
        output_template = str(obs.get("outtmpl", ""))
        output_template = output_template.replace("%(id)s", youtube_id)
        main_path = output_template
        main_path = main_path.replace(
            "%(ext)s", str(obs.get("merge_output_format", "mp4"))
        )
        if not os.path.splitext(main_path)[1]:
            main_path += f".{obs.get('merge_output_format', 'mp4')}"

        return {
            "extra_formats": extra_formats,
            "config": config,
            "temp_dir": temp_dir,
            "main_path": main_path,
            "format_sort": config.get("downloads", {}).get("format_sort"),
        }

    def post_download(
        self,
        context: dict[str, Any],
        youtube_id: str,
        dl_cache: str,
        success: bool,
    ) -> None:
        temp_dir = context.get("temp_dir")
        if not temp_dir:
            return

        try:
            if not success:
                return

            config = context["config"]
            tracks: list[tuple[str, str]] = []
            for language, format_id in context["extra_formats"].items():
                track_path = self._download_audio_track(
                    youtube_id,
                    format_id,
                    language,
                    temp_dir,
                    config,
                    context.get("format_sort"),
                )
                if track_path:
                    tracks.append((language, track_path))

            if tracks:
                # A failed merge is deliberately best-effort: the primary
                # download remains valid and is archived by core code.
                main_path = context["main_path"]
                if not os.path.isfile(main_path) and os.path.isdir(dl_cache):
                    candidates = sorted(
                        entry.path
                        for entry in os.scandir(dl_cache)
                        if entry.is_file()
                        and entry.name.startswith(youtube_id + ".")
                        and os.path.splitext(entry.name)[1].lower()
                        in {".mp4", ".mkv", ".webm", ".mov", ".ts"}
                        and not entry.name.endswith((".part", ".ytdl"))
                    )
                    if candidates:
                        main_path = candidates[0]
                merge_additional_audio_tracks(main_path, tracks)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _strip_pot_config(config: dict[str, Any]) -> dict[str, Any]:
        no_pot = copy.deepcopy(config)
        no_pot.setdefault("downloads", {}).pop("pot_provider_url", None)
        return no_pot

    @staticmethod
    def _download_audio_track(
        youtube_id: str,
        format_id: str,
        language: str,
        temp_dir: str,
        config: dict[str, Any],
        format_sort: str | None,
    ) -> str | None:
        safe_language = "".join(
            char if char.isalnum() or char in "-_" else "_"
            for char in language
        )
        base_name = f"{youtube_id}-{safe_language}"
        selector = f"bestaudio[language={language}]/{format_id}"
        track_obs: dict[str, Any] = {
            "format": selector,
            "outtmpl": os.path.join(temp_dir, f"{base_name}.%(ext)s"),
            "audio_multistreams": False,
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        if format_sort:
            track_obs["format_sort"] = [
                value.strip()
                for value in format_sort.split(",")
                if value.strip()
            ]

        no_pot_config = AudioTracksDownloadHook._strip_pot_config(config)
        success, _ = YtWrap(track_obs, no_pot_config).download(youtube_id)
        if not success:
            success, _ = YtWrap(track_obs, config).download(youtube_id)
        if not success:
            return None

        for entry in os.scandir(temp_dir):
            if (
                entry.name.startswith(base_name + ".")
                and not entry.name.endswith((".part", ".ytdl"))
                and entry.is_file()
            ):
                return entry.path
        return None
