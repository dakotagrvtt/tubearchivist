"""Data migrations owned by the audio-tracks feature."""

from __future__ import annotations

from typing import Any, Callable


def migrate_legacy_app_config(config: Any) -> list[str]:
    """Preserve the singular application key before old keys are pruned."""
    downloads = config.config.get("downloads", {})
    if (
        "audio_multistream" not in downloads
        or "audio_multistreams" in downloads
    ):
        return []

    value = downloads["audio_multistream"]
    config.update_config({"downloads": {"audio_multistreams": value}})
    return ["downloads.audio_multistream -> downloads.audio_multistreams"]


def migrate_legacy_channel_overwrites(
    run_migration: Callable[..., None],
) -> None:
    """Preserve singular channel overrides before removing their old key."""
    run_migration(
        index_name="ta_channel",
        desc="rename legacy audio_multistream channel overwrite",
        query={"exists": {"field": "channel_overwrites.audio_multistream"}},
        script={
            "source": """
                if (ctx._source.containsKey('channel_overwrites')) {
                    def overwrites = ctx._source.channel_overwrites;
                    if (!overwrites.containsKey('audio_multistreams')) {
                        overwrites.audio_multistreams =
                            overwrites.audio_multistream;
                    }
                    overwrites.remove('audio_multistream');
                }
            """,
            "lang": "painless",
        },
    )
