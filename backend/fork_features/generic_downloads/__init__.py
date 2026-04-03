"""generic_downloads – site-agnostic video downloads via yt-dlp.

Enables downloading individual video URLs from any website supported by
yt-dlp (e.g. Rumble, Vimeo, Dailymotion) without changing TubeArchivist's
core URL-parsing or download pipeline.

Two hooks are registered:

- ``url_resolver``: :class:`GenericUrlResolver` — intercepts non-YouTube URLs
  in the URL parser and resolves them to a ``(video_id, source_url)`` pair
  using yt-dlp's extractor.

- ``download_hook``: :class:`GenericDownloadHook` — ensures the full
  ``source_url`` is used as the yt-dlp download target rather than the bare
  video ID (which yt-dlp would otherwise try to resolve as a YouTube ID).
"""

from fork_features.registry import register

from .downloader import GenericDownloadHook
from .resolver import GenericUrlResolver

register(
    feature_id="generic_downloads",
    url_resolver=GenericUrlResolver(),
    download_hook=GenericDownloadHook(),
)
