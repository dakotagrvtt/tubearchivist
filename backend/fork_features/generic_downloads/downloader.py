"""
Functionality:
- DownloadHook for generic (non-YouTube) video downloads
- redirects the yt-dlp download target to the stored source_url when the
  pending-queue document contains one (i.e. the video came from a non-YouTube
  platform)
"""

from __future__ import annotations

from typing import Any

from common.src.es_connect import ElasticWrap


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
    ) -> dict[str, Any]:
        """Look up ``source_url`` from the pending queue and return as ``download_target``.

        Queries Elasticsearch for the pending document identified by
        *youtube_id*.  If the document has a ``source_url`` field the hook
        returns ``{"download_target": source_url}`` so the upstream downloader
        can use it as the actual yt-dlp URL.

        For YouTube videos (no ``source_url`` stored) the returned dict is
        empty and the upstream code falls back to the bare *youtube_id*.
        """
        path = f"ta_download/_doc/{youtube_id}"
        resp, _ = ElasticWrap(path).get(print_error=False)
        source_url: str | None = (
            (resp or {}).get("_source") or {}
        ).get("source_url")

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
