"""Thin startup integration surface for all fork-owned features."""

from __future__ import annotations

from typing import Any, Callable

from common.src.ta_redis import RedisArchivist
from fork_features.audio_tracks.migrations import (
    migrate_legacy_app_config,
    migrate_legacy_channel_overwrites,
)
from fork_features.audio_tracks.startup import (
    clear_stale_staging_directories,
)
from fork_features.playback.migrations import repair_legacy_media_paths
from fork_features.playback.startup import (
    clear_redis_state,
    ensure_cache_directory,
)


def run_config_migrations(config: Any) -> list[str]:
    """Run feature-owned config migrations before core prunes old keys."""
    return migrate_legacy_app_config(config)


def run_runtime_cleanup(stdout: Any, style: Any) -> None:
    """Prepare feature storage and reclaim interrupted runtime state."""
    ensure_cache_directory()
    playback_keys = clear_redis_state(RedisArchivist())
    audio_directories = clear_stale_staging_directories()
    if not playback_keys and not audio_directories:
        return

    if playback_keys:
        stdout.write(
            style.SUCCESS(f"    ✓ cleared {playback_keys} playback Redis keys")
        )
    if audio_directories:
        stdout.write(
            style.SUCCESS(
                "    ✓ cleared "
                f"{audio_directories} audio staging directories"
            )
        )


def run_data_repairs(
    run_migration: Callable[..., None], stdout: Any, style: Any
) -> None:
    """Run idempotent feature repairs regardless of the broad skip flag."""
    migrate_legacy_channel_overwrites(run_migration)
    repair_legacy_media_paths(stdout, style)
