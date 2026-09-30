"""Tests for application configuration cleanup at startup."""

import copy
from unittest.mock import Mock

import fork_features.audio_tracks  # noqa: F401
import fork_features.playback  # noqa: F401
import pytest
from appsettings.src import config


@pytest.fixture
def saved_config():
    """Representative saved settings, including fork-owned values."""
    return {
        "subscriptions": {"channel_size": 25, "auto_start": True},
        "downloads": {
            "format": "bestvideo+bestaudio",
            "container": "mkv",
            "audio_multistreams": True,
            "audio_languages": "en,es",
        },
        "application": {
            "enable_snapshot": False,
            "enable_fork_audio_tracks": False,
            "enable_fork_playback": True,
            "enable_fork_player": False,
            "enable_fork_multi_audio_playback": True,
        },
    }


@pytest.fixture
def app_config(saved_config):
    """Use real config logic without reading Elasticsearch."""
    instance = config.AppConfig.__new__(config.AppConfig)
    instance.config = copy.deepcopy(saved_config)
    return instance


@pytest.fixture
def elastic_wrap(monkeypatch):
    """Capture writes at the Elasticsearch service boundary."""
    wrapper = Mock()
    wrapper.return_value.post.return_value = ({"result": "updated"}, 200)
    monkeypatch.setattr(config, "ElasticWrap", wrapper)
    return wrapper


def test_clear_old_keys_removes_multiple_top_level_keys(
    app_config, saved_config, elastic_wrap
):
    """Removing top-level keys must not interrupt startup cleanup."""
    app_config.config = {
        "obsolete_first": {"enabled": True},
        **app_config.config,
        "obsolete_last": "legacy",
    }
    app_config.config["downloads"]["obsolete_nested"] = True

    cleared = app_config.clear_old_keys()

    assert cleared == [
        "{'obsolete_first': {'enabled': True}}",
        "downloads.obsolete_nested",
        "{'obsolete_last': 'legacy'}",
    ]
    assert app_config.config == saved_config
    elastic_wrap.assert_called_once_with(config.AppConfig.ES_PATH)
    elastic_wrap.return_value.post.assert_called_once_with(saved_config)


def test_clear_old_keys_preserves_registered_fork_settings(
    app_config, saved_config, elastic_wrap
):
    """Remove obsolete nested keys while retaining saved fork settings."""
    app_config.config["subscriptions"]["obsolete_size"] = 100
    app_config.config["downloads"]["audio_multistream"] = False
    app_config.config["downloads"]["obsolete_format"] = "old"
    app_config.config["application"]["obsolete_switch"] = True

    cleared = app_config.clear_old_keys()

    assert set(cleared) == {
        "subscriptions.obsolete_size",
        "downloads.audio_multistream",
        "downloads.obsolete_format",
        "application.obsolete_switch",
    }
    assert len(cleared) == 4
    assert app_config.config == saved_config
    elastic_wrap.assert_called_once_with(config.AppConfig.ES_PATH)
    elastic_wrap.return_value.post.assert_called_once_with(saved_config)


def test_clear_old_keys_does_not_persist_unchanged_config(
    app_config, saved_config, elastic_wrap
):
    """Already-clean settings remain unchanged without a service write."""
    assert app_config.clear_old_keys() == []

    assert app_config.config == saved_config
    elastic_wrap.assert_not_called()
