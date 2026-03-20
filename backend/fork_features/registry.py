"""
Fork Feature Registry

Provides a simple registry that fork features use to contribute:
  - Application config defaults (for AppConfig.CONFIG_DEFAULTS["downloads"])
  - App-level serializer fields (for AppConfigDownloadsSerializer)
  - Channel overwrite serializer fields (for ChannelOverwriteSerializer)
  - Channel overwrite index keys (for YoutubeChannel OVERWRITES list)
  - Download hooks (called before/after each video download)

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
    ) -> dict[str, Any]:
        """Called with the assembled yt-dlp obs *before* the download starts.

        Returns a *context* dict that is passed back verbatim to
        ``post_download``.
        """
        ...

    def post_download(
        self,
        context: dict[str, Any],
        youtube_id: str,
        dl_cache: str,
        success: bool,
    ) -> None:
        """Called immediately after yt-dlp returns.

        *context* is the dict returned by ``pre_download``.
        *dl_cache* is the absolute path to the download cache directory.
        *success* reflects whether yt-dlp reported a successful download.
        """
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
