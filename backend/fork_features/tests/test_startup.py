"""Tests for the shared fork startup adapter."""

from fork_features import startup


class _Output:
    def __init__(self):
        self.messages = []

    def write(self, message):
        self.messages.append(message)


class _Style:
    SUCCESS = staticmethod(str)


def test_runtime_cleanup_delegates_to_features(monkeypatch):
    """Keep runtime algorithms behind the single fork-owned adapter."""
    calls = []
    monkeypatch.setattr(
        startup, "ensure_cache_directory", lambda: calls.append("cache")
    )
    monkeypatch.setattr(startup, "RedisArchivist", lambda: "redis")
    monkeypatch.setattr(
        startup,
        "clear_redis_state",
        lambda redis: calls.append(redis) or 2,
    )
    monkeypatch.setattr(startup, "clear_stale_staging_directories", lambda: 1)
    output = _Output()

    startup.run_runtime_cleanup(output, _Style())

    assert calls == ["cache", "redis"]
    assert output.messages == [
        "    ✓ cleared 2 playback Redis keys",
        "    ✓ cleared 1 audio staging directories",
    ]


def test_data_repairs_delegate_to_each_owner(monkeypatch):
    """Run feature repairs independently of the core release skip flag."""
    calls = []
    runner = object()
    output = _Output()
    style = _Style()
    monkeypatch.setattr(
        startup,
        "migrate_legacy_channel_overwrites",
        lambda value: calls.append(("audio", value)),
    )
    monkeypatch.setattr(
        startup,
        "repair_legacy_media_paths",
        lambda stdout, selected_style: calls.append(
            ("playback", stdout, selected_style)
        ),
    )

    startup.run_data_repairs(runner, output, style)

    assert calls == [
        ("audio", runner),
        ("playback", output, style),
    ]
