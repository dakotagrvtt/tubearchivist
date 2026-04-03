"""
Fork Feature: Generic Downloads – channel fallback enricher

Implements the ChannelFallbackEnricher protocol from the fork registry.

When TubeArchivist downloads a video from a non-YouTube platform, it cannot
extract a full YouTube-style channel page.  Instead it calls
``YoutubeChannel._video_fallback()`` to build a minimal channel document from
the video's own yt-dlp metadata.

This enricher adds ``channel_source_url`` to that minimal document so that
future phases (subscription scanning, channel reindex) can re-crawl the
channel using the original platform URL rather than constructing an incorrect
YouTube URL from the synthesised channel ID.

The field is populated from yt-dlp's ``channel_url`` or ``uploader_url``
fields — both are commonly provided by non-YouTube extractors (e.g. Rumble
sets ``channel_url`` to ``https://rumble.com/c/ChannelName``).
"""

from __future__ import annotations

from typing import Any


class GenericChannelFallbackEnricher:
    """ChannelFallbackEnricher that stores the channel's source URL.

    Reads ``channel_url`` (preferred) or ``uploader_url`` from the raw
    yt-dlp video metadata dict and writes it as ``channel_source_url`` on
    the channel JSON document being built by ``_video_fallback()``.

    If neither field is present in the metadata (some extractors omit them)
    the enricher is a no-op and the channel document is left unchanged.
    """

    def enrich(
        self,
        channel_json: dict[str, Any],
        video_meta: dict[str, Any],
    ) -> None:
        """Add ``channel_source_url`` to *channel_json* when available."""
        channel_source_url: str | None = (
            video_meta.get("channel_url") or video_meta.get("uploader_url")
        )
        if not channel_source_url:
            return

        channel_json["channel_source_url"] = channel_source_url
        print(
            f"[generic_downloads] {channel_json.get('channel_id')}: "
            f"stored channel_source_url={channel_source_url!r}"
        )
