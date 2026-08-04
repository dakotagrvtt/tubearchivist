"""Celery discovery hook for the fork-owned playback task."""

from fork_features.playback.hls import prepare_hls_playback
from fork_features.playback.tasks import prepare_playback

__all__ = ["prepare_hls_playback", "prepare_playback"]
