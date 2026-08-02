"""Fork Feature: Audio Tracks – media stream metadata enrichment."""

from __future__ import annotations


class AudioTracksMediaStreamEnricher:
    """Extract useful language/title metadata for audio stream display."""

    def enrich_stream(
        self,
        stream: dict,
        metadata: dict,
    ) -> dict:
        """Augment audio stream metadata with UI-friendly fields."""
        tags = stream.get("tags") or {}
        if not isinstance(tags, dict):
            tags = {}

        bitrate_raw = stream.get("bit_rate")
        if not bitrate_raw:
            bps_tag = tags.get("BPS") or tags.get("BPS-eng")
            if bps_tag:
                try:
                    bitrate_raw = int(bps_tag)
                except (TypeError, ValueError):
                    bitrate_raw = 0
            else:
                bitrate_raw = 0

        language = (
            tags.get("language")
            or tags.get("LANGUAGE")
            or tags.get("Language")
            or tags.get("lang")
            or tags.get("LANG")
            or None
        )
        if isinstance(language, str):
            language = language.strip()
        if language and language.lower() == "und":
            language = None

        track_title = (
            tags.get("title")
            or tags.get("TITLE")
            or tags.get("Title")
            or tags.get("handler_name")
            or tags.get("HANDLER_NAME")
            or None
        )
        track_title = self._clean_audio_title(track_title)

        metadata.update(
            {
                "bitrate": int(bitrate_raw),
                "language": language,
                "title": track_title,
                "channels": stream.get("channels"),
                "channel_layout": stream.get("channel_layout"),
            }
        )
        return metadata

    @staticmethod
    def _clean_audio_title(track_title: str | None) -> str | None:
        """Remove noisy/generic titles that are not useful in the UI."""
        if not isinstance(track_title, str) or not track_title:
            return None

        cleaned = track_title.strip()
        if not cleaned:
            return None

        lower = cleaned.lower()
        noisy_titles = {
            "iso media file produced by google inc.",
            "soundhandler",
            "iso media",
        }
        if lower in noisy_titles:
            return None

        return cleaned
