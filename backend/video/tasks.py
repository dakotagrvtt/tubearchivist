"""Celery discovery hook for the fork-owned playback task."""

from fork_features.playback.tasks import prepare_playback

__all__ = ["prepare_playback"]
