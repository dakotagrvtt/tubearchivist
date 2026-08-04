"""Fork-owned asynchronous and range-capable playback feature."""

from fork_features.playback.chapters import ChaptersMetadataEnricher
from fork_features.playback.playlist_nav import PlaylistNavEnricher
from fork_features.registry import register
from rest_framework import serializers

register(
    feature_id="playback",
    application_config_defaults={
        "enable_fork_playback": True,
        "enable_fork_player": True,
    },
    application_serializer_fields={
        "enable_fork_playback": serializers.BooleanField(required=False),
        "enable_fork_player": serializers.BooleanField(required=False),
    },
    enabled_config_key="enable_fork_playback",
    video_metadata_enricher=ChaptersMetadataEnricher(),
    playlist_nav_enricher=PlaylistNavEnricher(),
)

register(
    feature_id="multi_audio_playback",
    application_config_defaults={"enable_fork_multi_audio_playback": True},
    application_serializer_fields={
        "enable_fork_multi_audio_playback": serializers.BooleanField(
            required=False
        )
    },
    enabled_config_key="enable_fork_multi_audio_playback",
)
