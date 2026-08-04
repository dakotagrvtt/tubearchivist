"""Tests for fork feature registration and master switches."""

import fork_features.audio_tracks  # noqa: F401
import fork_features.playback  # noqa: F401
from appsettings.serializers import AppConfigSerializer
from appsettings.src.config import AppConfig
from fork_features.registry import (
    get_application_config_defaults,
    get_application_serializer_fields,
    get_download_hooks,
    is_feature_enabled,
)


def test_fork_feature_flags_are_default_on():
    defaults = get_application_config_defaults()

    assert defaults == {
        "enable_fork_audio_tracks": True,
        "enable_fork_player": True,
        "enable_fork_playback": True,
    }
    assert set(get_application_serializer_fields()) == set(defaults)

    serializer_fields = AppConfigSerializer().fields["application"].fields
    assert set(defaults).issubset(serializer_fields)

    effective = AppConfig.__new__(AppConfig)._effective_defaults()
    assert effective["application"]["enable_fork_audio_tracks"] is True
    assert effective["application"]["enable_fork_player"] is True
    assert effective["application"]["enable_fork_playback"] is True


def test_disabled_audio_feature_blocks_download_hook():
    config = {
        "application": {"enable_fork_audio_tracks": False},
        "downloads": {"audio_multistreams": True},
    }

    assert not is_feature_enabled("audio_tracks", config)
    assert get_download_hooks(config) == []


def test_missing_flag_keeps_existing_installations_enabled():
    assert is_feature_enabled("audio_tracks", {"application": {}})
    assert is_feature_enabled("playback", {})
