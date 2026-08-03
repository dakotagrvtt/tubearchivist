"""Runtime cleanup owned by the audio-tracks feature."""

from __future__ import annotations

import os
import shutil
import tempfile


def clear_stale_staging_directories() -> int:
    """Remove staging directories left by interrupted workers."""
    removed = 0
    try:
        entries = os.scandir(tempfile.gettempdir())
    except OSError:
        return removed

    with entries:
        for entry in entries:
            if not entry.is_dir() or not entry.name.startswith("ta-audio-"):
                continue
            shutil.rmtree(entry.path, ignore_errors=True)
            if not os.path.exists(entry.path):
                removed += 1

    return removed
