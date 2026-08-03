"""Tests for audio-track configuration migrations."""

from fork_features.audio_tracks.migrations import (
    migrate_legacy_app_config,
    migrate_legacy_channel_overwrites,
)


class _Config:
    def __init__(self, downloads):
        self.config = {"downloads": downloads}
        self.updates = []

    def update_config(self, update):
        self.updates.append(update)


def test_migrate_legacy_app_config_preserves_value():
    """Copy the singular setting before core removes it."""
    config = _Config({"audio_multistream": True})

    result = migrate_legacy_app_config(config)

    assert config.updates == [{"downloads": {"audio_multistreams": True}}]
    assert result == [
        "downloads.audio_multistream -> downloads.audio_multistreams"
    ]


def test_migrate_legacy_app_config_keeps_existing_plural():
    """Never overwrite an already migrated plural value."""
    config = _Config({"audio_multistream": True, "audio_multistreams": False})

    assert migrate_legacy_app_config(config) == []
    assert config.updates == []


def test_channel_migration_is_feature_owned():
    """Describe the idempotent Elasticsearch update through the core runner."""
    captured = {}

    def run_migration(**kwargs):
        captured.update(kwargs)

    migrate_legacy_channel_overwrites(run_migration)

    assert captured["index_name"] == "ta_channel"
    assert captured["query"] == {
        "exists": {"field": "channel_overwrites.audio_multistream"}
    }
    assert "audio_multistreams" in captured["script"]["source"]
    assert (
        "overwrites.remove('audio_multistream')"
        in captured["script"]["source"]
    )
