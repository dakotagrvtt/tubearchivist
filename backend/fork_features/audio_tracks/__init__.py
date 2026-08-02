"""
Fork Feature: Audio Tracks

Adds the ability to archive multiple audio language tracks in the configured
container, with both global and per-channel settings support.

This module self-registers when imported.  It is imported via
``backend/fork_features/apps.py`` (a Django AppConfig), which means it is
loaded automatically when Django starts as long as
``fork_features`` is listed in ``INSTALLED_APPS``.
"""

from rest_framework import serializers

from fork_features.audio_tracks.downloader import AudioTracksDownloadHook
from fork_features.audio_tracks.media_streams import (
    AudioTracksMediaStreamEnricher,
)
from fork_features.registry import register

register(
    feature_id="audio_tracks",
    config_defaults={
        "audio_multistreams": False,
        "audio_languages": None,
    },
    app_serializer_fields={
        "audio_multistreams": serializers.BooleanField(
            required=False
        ),
        "audio_languages": serializers.CharField(
            required=False, allow_null=True
        ),
    },
    channel_serializer_fields={
        "audio_multistreams": serializers.BooleanField(
            required=False, allow_null=True
        ),
        "audio_languages": serializers.CharField(
            required=False, allow_null=True
        ),
    },
    channel_overwrite_keys=["audio_multistreams", "audio_languages"],
    download_hook=AudioTracksDownloadHook(),
    media_stream_enricher=AudioTracksMediaStreamEnricher(),
)
