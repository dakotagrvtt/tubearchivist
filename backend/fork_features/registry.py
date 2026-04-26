"""
Fork Feature Registry

Provides a simple registry that fork features use to contribute:
  - Application config defaults (for AppConfig.CONFIG_DEFAULTS["downloads"])
  - App-level serializer fields (for AppConfigDownloadsSerializer)
  - Channel overwrite serializer fields (for ChannelOverwriteSerializer)
  - Channel overwrite index keys (for YoutubeChannel OVERWRITES list)
  - Download hooks (called before/after each video download)
  - Media stream enrichers (augment ffprobe stream metadata for UI display)

Usage
-----
To register a feature, call ``register()`` from your feature module's
top-level code (typically in its own ``__init__.py``).  All registrations
must happen before Django finishes startup; importing this module in
``backend/config/urls.py`` or the Django app-ready signal is the easiest way.

The core integration points import from this module directly so there is no
circular-import risk.

Example (see FORK_FEATURES.md for a full walkthrough)::

    from fork_features.registry import register

    register(
        feature_id="audio_tracks",
        config_defaults={"audio_multistreams": False, "audio_languages": None},
        app_serializer_fields={"audio_multistreams": ..., "audio_languages": ...},
        channel_serializer_fields={"audio_multistreams": ..., "audio_languages": ...},
        channel_overwrite_keys=["audio_multistreams", "audio_languages"],
        download_hook=MyFeatureDownloadHook(),
        media_stream_enricher=MyMediaStreamEnricher(),
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from rest_framework import serializers as drf_serializers


# ---------------------------------------------------------------------------
# Download hook protocol
# ---------------------------------------------------------------------------


class DownloadHook(Protocol):
    """Protocol that fork-feature download hooks must satisfy.

    Hooks are called once per video, in registration order.  A hook may
    mutate *obs* in-place to alter yt-dlp behaviour and may store arbitrary
    state on *context* (a plain dict shared across hook calls for the same
    video) that it retrieves again in ``post_download``.
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
        """Called with the assembled yt-dlp obs *before* the download starts.

        Returns a *context* dict that is passed back verbatim to
        ``post_download``. ``pending_video`` contains the pending queue
        document from Elasticsearch, so hooks can avoid duplicate datastore
        lookups.
        """
        ...


class UrlResolver(Protocol):
    """Protocol that fork-feature URL resolvers must satisfy.

    Resolvers are consulted by the URL parser when a URL does not belong to
    a natively-supported domain (e.g. a non-YouTube URL).  The first resolver
    that returns ``True`` from ``can_resolve`` wins.
    """

    def can_resolve(self, netloc: str) -> bool:
        """Return True if this resolver can handle URLs on *netloc*."""
        ...

    def resolve(self, url: str) -> "ParsedURLType":
        """Resolve *url* and return a :class:`ParsedURLType` dict.

        The ``url`` field inside the returned dict should be the platform's
        native video/item ID (used as ``youtube_id`` throughout the system).
        Include a ``source_url`` key with the original full URL so that
        re-downloads can reconstruct the correct address.
        """
        ...


class MediaStreamEnricher(Protocol):
    """Protocol for augmenting extracted media stream metadata.

    Enrichers are called for each parsed ffprobe stream after the core code
    has assembled the base metadata dict. They may mutate and/or return the
    metadata dict with extra keys used by fork-specific UI.
    """

    def enrich_stream(
        self,
        stream: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Return enriched metadata for a single stream."""
        ...


class ChannelFallbackEnricher(Protocol):
    """Protocol for enriching channel documents built from video metadata.

    Called inside ``YoutubeChannel._video_fallback()`` after the minimal
    channel dict has been assembled from yt-dlp video metadata.  Enrichers
    may mutate *channel_json* in-place to add fork-specific fields (e.g.
    ``channel_source_url`` for non-YouTube channels).
    """

    def enrich(
        self,
        channel_json: dict[str, Any],
        video_meta: dict[str, Any],
    ) -> None:
        """Mutate *channel_json* in-place using raw yt-dlp *video_meta*."""
        ...


# ---------------------------------------------------------------------------
# Registry entry
# ---------------------------------------------------------------------------


@dataclass
class _FeatureEntry:
    feature_id: str
    config_defaults: dict[str, Any] = field(default_factory=dict)
    app_serializer_fields: dict[str, Any] = field(default_factory=dict)
    channel_serializer_fields: dict[str, Any] = field(default_factory=dict)
    channel_overwrite_keys: list[str] = field(default_factory=list)
    download_hook: DownloadHook | None = None
    url_resolver: UrlResolver | None = None
    media_stream_enricher: MediaStreamEnricher | None = None
    channel_fallback_enricher: ChannelFallbackEnricher | None = None


# ---------------------------------------------------------------------------
# Global registry
# ---------------------------------------------------------------------------

_registry: list[_FeatureEntry] = []


def register(
    feature_id: str,
    *,
    config_defaults: dict[str, Any] | None = None,
    app_serializer_fields: dict[str, "drf_serializers.Field"] | None = None,
    channel_serializer_fields: dict[str, "drf_serializers.Field"] | None = None,
    channel_overwrite_keys: list[str] | None = None,
    download_hook: DownloadHook | None = None,
    url_resolver: UrlResolver | None = None,
    media_stream_enricher: MediaStreamEnricher | None = None,
    channel_fallback_enricher: ChannelFallbackEnricher | None = None,
) -> None:
    """Register a fork feature.

    Parameters
    ----------
    feature_id:
        Unique string identifier for this feature (used in logs/errors).
    config_defaults:
        Key-value pairs to merge into
        ``AppConfig.CONFIG_DEFAULTS["downloads"]``.
    app_serializer_fields:
        DRF ``Field`` instances to add to ``AppConfigDownloadsSerializer``.
    channel_serializer_fields:
        DRF ``Field`` instances to add to ``ChannelOverwriteSerializer``.
    channel_overwrite_keys:
        Keys that should be copied from ES channel doc into the
        ``channel_overwrites`` dict used during download.
    download_hook:
        Object implementing :class:`DownloadHook` that is called around
        each video download.
    url_resolver:
        Object implementing :class:`UrlResolver` consulted by the URL parser
        when a URL does not match any natively-supported domain.
    media_stream_enricher:
        Object implementing :class:`MediaStreamEnricher` that can enrich
        ffprobe-derived stream metadata for display in the UI.
    channel_fallback_enricher:
        Object implementing :class:`ChannelFallbackEnricher` called inside
        ``YoutubeChannel._video_fallback()`` to add fork-specific fields to
        channel documents created from video metadata.
    """
    for existing in _registry:
        if existing.feature_id == feature_id:
            raise ValueError(
                f"Fork feature '{feature_id}' is already registered."
            )

    _registry.append(
        _FeatureEntry(
            feature_id=feature_id,
            config_defaults=config_defaults or {},
            app_serializer_fields=app_serializer_fields or {},
            channel_serializer_fields=channel_serializer_fields or {},
            channel_overwrite_keys=list(channel_overwrite_keys or []),
            download_hook=download_hook,
            url_resolver=url_resolver,
            media_stream_enricher=media_stream_enricher,
            channel_fallback_enricher=channel_fallback_enricher,
        )
    )
    print(f"[fork_features] registered feature: {feature_id}")


# ---------------------------------------------------------------------------
# Aggregated accessors used by core integration points
# ---------------------------------------------------------------------------


def get_config_defaults() -> dict[str, Any]:
    """Merged downloads-config defaults from all registered features."""
    merged: dict[str, Any] = {}
    for entry in _registry:
        merged.update(entry.config_defaults)
    return merged


def get_app_serializer_fields() -> dict[str, Any]:
    """All app-settings serializer fields from registered features."""
    merged: dict[str, Any] = {}
    for entry in _registry:
        merged.update(entry.app_serializer_fields)
    return merged


def get_channel_serializer_fields() -> dict[str, Any]:
    """All channel-overwrite serializer fields from registered features."""
    merged: dict[str, Any] = {}
    for entry in _registry:
        merged.update(entry.channel_serializer_fields)
    return merged


def get_channel_overwrite_keys() -> list[str]:
    """All channel-overwrite index keys from registered features."""
    keys: list[str] = []
    for entry in _registry:
        for k in entry.channel_overwrite_keys:
            if k not in keys:
                keys.append(k)
    return keys


def get_download_hooks() -> list[DownloadHook]:
    """Download hooks from registered features (in registration order)."""
    return [
        entry.download_hook
        for entry in _registry
        if entry.download_hook is not None
    ]


def get_url_resolvers() -> list[UrlResolver]:
    """URL resolvers from registered features (in registration order)."""
    return [
        entry.url_resolver
        for entry in _registry
        if entry.url_resolver is not None
    ]


def get_media_stream_enrichers() -> list[MediaStreamEnricher]:
    """Media stream enrichers from registered features."""
    return [
        entry.media_stream_enricher
        for entry in _registry
        if entry.media_stream_enricher is not None
    ]


def get_channel_fallback_enrichers() -> list[ChannelFallbackEnricher]:
    """Channel fallback enrichers from registered features."""
    return [
        entry.channel_fallback_enricher
        for entry in _registry
        if entry.channel_fallback_enricher is not None
    ]
