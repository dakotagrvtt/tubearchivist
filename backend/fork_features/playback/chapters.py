"""Normalize yt-dlp chapters for the fork playback UI."""

from __future__ import annotations

from typing import Any


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def normalize_chapters(
    raw_chapters: Any, duration: Any = None
) -> list[dict[str, float | str]]:
    """Return safe, ordered chapter intervals suitable for WebVTT."""
    if not isinstance(raw_chapters, list):
        return []

    duration_value = _number(duration)
    if duration_value is not None:
        duration_value = max(duration_value, 0)

    candidates: list[tuple[float, float | None, str]] = []
    for index, raw in enumerate(raw_chapters):
        if not isinstance(raw, dict):
            continue
        start = _number(raw.get("start_time"))
        if start is None:
            start = _number(raw.get("start"))
        if start is None:
            continue
        end = _number(raw.get("end_time"))
        if end is None:
            end = _number(raw.get("end"))
        title = str(raw.get("title") or f"Chapter {index + 1}").strip()
        candidates.append(
            (max(start, 0), end, title or f"Chapter {index + 1}")
        )

    candidates.sort(key=lambda item: item[0])
    normalized: list[dict[str, float | str]] = []
    for index, (start, explicit_end, title) in enumerate(candidates):
        if duration_value is not None:
            start = min(start, duration_value)
        next_start = (
            candidates[index + 1][0] if index + 1 < len(candidates) else None
        )
        end = explicit_end if explicit_end is not None else next_start
        if end is None:
            end = duration_value
        if end is None:
            continue
        end = max(
            min(end, duration_value) if duration_value is not None else end, 0
        )
        if end <= start:
            continue
        if normalized and start < float(normalized[-1]["end"]):
            start = float(normalized[-1]["end"])
        if end <= start:
            continue
        normalized.append({"start": start, "end": end, "title": title})

    return normalized


class ChaptersMetadataEnricher:
    """Index only chapter labels and time ranges; never creates images."""

    def enrich_metadata(
        self, metadata: dict[str, Any], video: dict[str, Any]
    ) -> dict[str, Any]:
        chapters = normalize_chapters(
            metadata.get("chapters"), metadata.get("duration")
        )
        if chapters:
            video["chapters"] = chapters
        else:
            video.pop("chapters", None)
        return video
