"""Fork-owned asynchronous and range-capable playback feature."""

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
)
