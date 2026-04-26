"""
Functionality:
- DownloadHook for generic (non-YouTube) video downloads
- redirects the yt-dlp download target to the stored source_url when the
  pending-queue document contains one (i.e. the video came from a non-YouTube
  platform)
"""

from __future__ import annotations

from typing import Any


class GenericDownloadHook:
    """Use the stored ``source_url`` as the yt-dlp download target.

    For non-YouTube videos the pending-queue document in Elasticsearch
    contains a ``source_url`` field with the original full URL.  yt-dlp
    needs that full URL (not just the bare video ID) to download from sites
    other than YouTube — passing a bare ID would cause yt-dlp to treat it as
    a YouTube search term.

    Returning ``{"download_target": source_url}`` from ``pre_download`` tells
    the upstream ``_dl_single_vid`` to use that URL instead of the bare
    ``youtube_id`` when calling ``YtWrap.download()``.
    """

    def pre_download(
        self,
        obs: dict[str, Any],
        youtube_id: str,
        channel_id: str,
        config: dict[str, Any],
        channel_overwrites: dict[str, dict[str, Any]],
        pending_video: dict[str, Any],
    ) -> dict[str, Any]:
        """Return ``download_target`` from pending metadata when available.

        For YouTube videos (no ``source_url`` stored) the returned dict is
        empty and the upstream code falls back to the bare *youtube_id*.
        """
        source_url: str | None = pending_video.get("source_url")

        if source_url:
            print(
                f"[generic_downloads] {youtube_id}: "
                f"using source_url as download target: {source_url!r}"
            )
            return {"download_target": source_url}

        return {}

    def post_download(
        self,
        context: dict[str, Any],
        youtube_id: str,
        dl_cache: str,
        success: bool,
    ) -> None:
        """No post-download action required for this hook."""
