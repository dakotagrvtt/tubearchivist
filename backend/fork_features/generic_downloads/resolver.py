"""
Functionality:
- resolve any yt-dlp-supported URL that is not natively handled by
  TubeArchivist's URL parser (i.e. non-YouTube URLs)
- implements the UrlResolver protocol for the fork_features registry
"""

from __future__ import annotations

from download.src.yt_dlp_base import YtWrap
from video.src.constants import VideoTypeEnum

# Domains that TubeArchivist handles natively — the resolver will not claim
# these and lets the core parser handle them as usual.
_YOUTUBE_NETLOCS: frozenset[str] = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
)


class GenericUrlResolver:
    """Resolve any yt-dlp-supported URL to a (video_id, source_url) pair.

    This resolver is consulted by the URL parser when a URL does not belong
    to a natively-supported domain.  It uses a lightweight yt-dlp probe
    (``skip_download=True``, ``noplaylist=True``) to obtain the canonical
    video ID and basic metadata without triggering a download.

    The returned dict is a ``ParsedURLType``-compatible mapping with an extra
    ``source_url`` key containing the original URL so that re-downloads work
    correctly on non-YouTube platforms.
    """

    def can_resolve(self, netloc: str) -> bool:
        """Return ``True`` for any domain that is not a native YouTube domain."""
        # Normalise — strip port and leading 'www.' for comparison.
        bare = netloc.lower().split(":")[0]
        if bare.startswith("www."):
            bare = bare[4:]
        return bare not in {d.removeprefix("www.") for d in _YOUTUBE_NETLOCS}

    def resolve(self, url: str) -> dict:
        """Probe *url* with yt-dlp and return a ``ParsedURLType``-compatible dict.

        The ``url`` key in the returned mapping is the platform-native video
        ID (used as ``youtube_id`` throughout the system).  ``source_url``
        holds the original full URL so the downloader can reconstruct the
        correct address when it is time to actually fetch the file.

        Parameters
        ----------
        url:
            The full URL as entered by the user (e.g.
            ``https://rumble.com/v3hq6ue-some-title.html``).

        Returns
        -------
        dict
            A ``ParsedURLType``-compatible dict with keys
            ``type``, ``url``, ``vid_type``, and ``source_url``.

        Raises
        ------
        ValueError
            If yt-dlp cannot resolve the URL or returns no ``id``.
        """
        obs: dict = {
            "skip_download": True,
            "noplaylist": True,
            "check_formats": None,
        }
        info, error = YtWrap(obs).extract(url)

        if not info:
            raise ValueError(
                f"[generic_downloads] yt-dlp could not resolve URL "
                f"{url!r}: {error}"
            )

        video_id = info.get("id")
        if not video_id:
            raise ValueError(
                f"[generic_downloads] yt-dlp returned no ID for URL: {url!r}"
            )

        vid_type = self._detect_vid_type(info)
        print(
            f"[generic_downloads] resolved {url!r} "
            f"→ id={video_id!r} ({vid_type.value})"
        )

        return {
            "type": "video",
            "url": video_id,
            "vid_type": vid_type,
            "source_url": url,
        }

    @staticmethod
    def _detect_vid_type(info: dict) -> VideoTypeEnum:
        """Best-effort ``VideoTypeEnum`` detection from yt-dlp metadata."""
        if info.get("live_status") == "was_live":
            return VideoTypeEnum.STREAMS
        return VideoTypeEnum.VIDEOS
