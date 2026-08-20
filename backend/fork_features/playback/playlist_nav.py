"""Playlist navigation data used by the fork player controls."""

from __future__ import annotations

from typing import Any


class PlaylistNavEnricher:
    """Expose the ordered downloaded queue without changing
    playlist storage."""

    def enrich_nav(
        self, nav: dict[str, Any], playlist: dict[str, Any]
    ) -> dict[str, Any]:
        entries = playlist.get("playlist_entries", [])
        nav["playlist_entries"] = [
            {
                "youtube_id": entry["youtube_id"],
                "title": entry.get("title", ""),
                "uploader": entry.get("uploader"),
                "idx": entry["idx"],
                "downloaded": entry["downloaded"],
            }
            for entry in entries
            if entry.get("downloaded")
        ]
        return nav
