"""
Fork Feature: Audio Tracks – ffmpeg merge helpers

Handles:
- Counting existing audio streams in a media file (via ffprobe)
- Merging extra audio tracks into the configured primary container (via ffmpeg)
"""

from __future__ import annotations

import os
import subprocess

from fork_features.audio_tracks.languages import (
    language_title,
    normalize_language_code,
)


def count_audio_streams(path: str) -> int:
    """Count existing audio streams in a media file using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return 0

    output = result.stdout.strip()
    if not output:
        return 0

    return len(output.splitlines())


def merge_additional_audio_tracks(  # noqa: C901
    main_path: str, audio_tracks: list[tuple[str, str]]
) -> bool:
    """Merge extra audio tracks into the configured primary file via ffmpeg.

    - Maps all streams from the main file.
    - Appends the first audio stream from each fallback file.
    - Stream-copies only (no re-encode), preserving the primary extension.
    - Labels appended tracks with ISO-639-2 language codes and human titles.

    Returns True on success, False on failure.
    """
    if not os.path.isfile(main_path) or not audio_tracks:
        return False

    extension = os.path.splitext(main_path)[1] or ".mkv"
    output_path = f"{main_path}.merging{extension}"
    cmd = ["ffmpeg", "-y", "-i", main_path]
    for _, track_path in audio_tracks:
        cmd += ["-i", track_path]

    cmd += ["-map", "0"]
    for input_idx in range(1, len(audio_tracks) + 1):
        cmd += ["-map", f"{input_idx}:a:0"]

    existing_audio_count = count_audio_streams(main_path)
    for idx, (lang, _) in enumerate(audio_tracks):
        audio_stream_idx = existing_audio_count + idx
        language_code = normalize_language_code(lang)
        lang_title = language_title(lang)
        cmd += [
            f"-metadata:s:a:{audio_stream_idx}",
            f"language={language_code}",
            f"-metadata:s:a:{audio_stream_idx}",
            f"title={lang_title}",
        ]

    cmd += ["-c", "copy", output_path]

    print(f"[audio_languages] ffmpeg merge: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        err = str(stderr)
        print(f"[audio_languages] ffmpeg merge failed: {err}")
        try:
            os.remove(output_path)
        except FileNotFoundError:
            pass
        return False

    try:
        os.replace(output_path, main_path)
    except OSError as error:
        print(f"[audio_languages] failed to replace primary media: {error}")
        try:
            os.remove(output_path)
        except FileNotFoundError:
            pass
        return False
    return True
