"""Registry for fork-only extensions.

The registry is deliberately small.  Core TubeArchivist code asks it for
contributions at explicit integration points, while feature implementations
remain isolated under :mod:`fork_features`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from rest_framework import serializers as drf_serializers


class DownloadHook(Protocol):
    """Lifecycle hooks around one yt-dlp download.

    ``pre_download`` may mutate the options dictionary and returns private
    state for the matching ``post_download`` call.  Hooks must not assume
    that the primary download succeeded; cleanup is performed for both
    outcomes.
    """

    def pre_download(
        self,
        obs: dict[str, Any],
        youtube_id: str,
        channel_id: str,
        config: dict[str, Any],
        channel_overwrites: dict[str, dict[str, Any]],
    ) -> dict[str, Any]: ...

    def post_download(
        self,
        context: dict[str, Any],
        youtube_id: str,
        dl_cache: str,
        success: bool,
    ) -> None: ...


class MediaStreamEnricher(Protocol):
    """Add feature-owned fields to one ffprobe audio stream."""

    def enrich_stream(
        self, stream: dict[str, Any], metadata: dict[str, Any]
    ) -> dict[str, Any]: ...


@dataclass
class _FeatureEntry:
    feature_id: str
    config_defaults: dict[str, Any] = field(default_factory=dict)
    app_serializer_fields: dict[str, Any] = field(default_factory=dict)
    application_config_defaults: dict[str, Any] = field(default_factory=dict)
    application_serializer_fields: dict[str, Any] = field(default_factory=dict)
    channel_serializer_fields: dict[str, Any] = field(default_factory=dict)
    channel_overwrite_keys: list[str] = field(default_factory=list)
    enabled_config_key: str | None = None
    download_hook: DownloadHook | None = None
    media_stream_enricher: MediaStreamEnricher | None = None


_registry: list[_FeatureEntry] = []


def _check_unique(feature_id: str, values: list[str], kind: str) -> None:
    seen: set[str] = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        names = ", ".join(sorted(duplicates))
        raise ValueError(
            f"Fork feature '{feature_id}' declares duplicate {kind}: {names}"
        )

    scope_by_kind = {
        "config defaults": "downloads",
        "app serializer fields": "downloads",
        "application config defaults": "application",
        "application serializer fields": "application",
        "channel serializer fields": "channel",
        "channel overwrite keys": "channel",
    }
    scope = scope_by_kind[kind]
    for existing in _registry:
        if scope == "downloads":
            existing_values = set(existing.config_defaults) | set(
                existing.app_serializer_fields
            )
        elif scope == "application":
            existing_values = set(existing.application_config_defaults) | set(
                existing.application_serializer_fields
            )
        else:
            existing_values = set(existing.channel_serializer_fields) | set(
                existing.channel_overwrite_keys
            )
        overlap = set(values) & existing_values
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(
                f"Fork feature '{feature_id}' conflicts with "
                f"'{existing.feature_id}' in {kind}: {names}"
            )


def register(
    feature_id: str,
    *,
    config_defaults: dict[str, Any] | None = None,
    app_serializer_fields: dict[str, "drf_serializers.Field"] | None = None,
    application_config_defaults: dict[str, Any] | None = None,
    application_serializer_fields: (
        dict[str, "drf_serializers.Field"] | None
    ) = None,
    channel_serializer_fields: (
        dict[str, "drf_serializers.Field"] | None
    ) = None,
    channel_overwrite_keys: list[str] | None = None,
    enabled_config_key: str | None = None,
    download_hook: DownloadHook | None = None,
    media_stream_enricher: MediaStreamEnricher | None = None,
) -> None:
    """Register one feature and fail early on contribution collisions."""
    if any(entry.feature_id == feature_id for entry in _registry):
        raise ValueError(f"Fork feature '{feature_id}' is already registered.")

    defaults = dict(config_defaults or {})
    app_fields = dict(app_serializer_fields or {})
    application_defaults = dict(application_config_defaults or {})
    application_fields = dict(application_serializer_fields or {})
    channel_fields = dict(channel_serializer_fields or {})
    overwrite_keys = list(channel_overwrite_keys or [])
    _check_unique(feature_id, list(defaults), "config defaults")
    _check_unique(feature_id, list(app_fields), "app serializer fields")
    _check_unique(
        feature_id,
        list(application_defaults),
        "application config defaults",
    )
    _check_unique(
        feature_id,
        list(application_fields),
        "application serializer fields",
    )
    _check_unique(
        feature_id, list(channel_fields), "channel serializer fields"
    )
    _check_unique(feature_id, overwrite_keys, "channel overwrite keys")

    _registry.append(
        _FeatureEntry(
            feature_id=feature_id,
            config_defaults=defaults,
            app_serializer_fields=app_fields,
            application_config_defaults=application_defaults,
            application_serializer_fields=application_fields,
            channel_serializer_fields=channel_fields,
            channel_overwrite_keys=overwrite_keys,
            enabled_config_key=enabled_config_key,
            download_hook=download_hook,
            media_stream_enricher=media_stream_enricher,
        )
    )
    print(f"[fork_features] registered feature: {feature_id}")


def get_config_defaults() -> dict[str, Any]:
    """Return all feature-owned download defaults."""
    merged: dict[str, Any] = {}
    for entry in _registry:
        merged.update(entry.config_defaults)
    return merged


def get_app_serializer_fields() -> dict[str, Any]:
    """Return all feature-owned application serializer fields."""
    merged: dict[str, Any] = {}
    for entry in _registry:
        merged.update(entry.app_serializer_fields)
    return merged


def get_application_config_defaults() -> dict[str, Any]:
    """Return all feature-owned application defaults."""
    merged: dict[str, Any] = {}
    for entry in _registry:
        merged.update(entry.application_config_defaults)
    return merged


def get_application_serializer_fields() -> dict[str, Any]:
    """Return all feature-owned application serializer fields."""
    merged: dict[str, Any] = {}
    for entry in _registry:
        merged.update(entry.application_serializer_fields)
    return merged


def is_feature_enabled(feature_id: str, config: dict[str, Any]) -> bool:
    """Resolve a feature's application-level master switch.

    Missing keys intentionally use the registered default. This keeps older
    configurations enabled during the short window before startup adds the
    new defaults to Elasticsearch.
    """
    entry = next(
        (
            candidate
            for candidate in _registry
            if candidate.feature_id == feature_id
        ),
        None,
    )
    if entry is None or entry.enabled_config_key is None:
        return True

    default = entry.application_config_defaults.get(
        entry.enabled_config_key, True
    )
    application = config.get("application", {})
    return bool(application.get(entry.enabled_config_key, default))


def get_channel_serializer_fields() -> dict[str, Any]:
    """Return all feature-owned channel serializer fields."""
    merged: dict[str, Any] = {}
    for entry in _registry:
        merged.update(entry.channel_serializer_fields)
    return merged


def get_channel_overwrite_keys() -> list[str]:
    """Return unique channel-overwrite keys in registration order."""
    keys: list[str] = []
    for entry in _registry:
        keys.extend(entry.channel_overwrite_keys)
    return keys


def get_download_hooks(
    config: dict[str, Any] | None = None,
) -> list[DownloadHook]:
    """Return enabled download hooks in registration order."""
    return [
        entry.download_hook
        for entry in _registry
        if entry.download_hook is not None
        and is_feature_enabled(entry.feature_id, config or {})
    ]


def get_media_stream_enrichers() -> list[MediaStreamEnricher]:
    """Return media stream enrichers in registration order."""
    return [
        entry.media_stream_enricher
        for entry in _registry
        if entry.media_stream_enricher is not None
    ]
