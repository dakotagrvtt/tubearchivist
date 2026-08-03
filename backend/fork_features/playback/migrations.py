"""Startup data repair for legacy playback media paths."""

from __future__ import annotations

import json
from typing import Any

from common.src.es_connect import ElasticWrap, IndexPaginate
from fork_features.playback.media_paths import (
    normalize_media_url,
    resolve_archived_media_path,
)


def repair_legacy_media_paths(stdout: Any, style: Any) -> None:
    """Repair indexed MKV paths when the archive contains an MP4."""
    stdout.write("[MIGRATION] run repair legacy indexed media extensions")
    data = {
        "_source": ["youtube_id", "media_url"],
        "query": {
            "wildcard": {
                "media_url": {
                    "value": "*.mkv",
                    "case_insensitive": True,
                }
            }
        },
    }
    videos = IndexPaginate("ta_video", data=data).get_results()
    bulk_lines: list[str] = []
    for video in videos:
        video_id = video.get("youtube_id")
        media_url = video.get("media_url")
        if not video_id or not media_url:
            continue

        resolved = resolve_archived_media_path(media_url, video_id)
        if not resolved:
            continue
        resolved_media_url, _ = resolved
        if resolved_media_url == normalize_media_url(media_url):
            continue

        bulk_lines.extend(
            [
                json.dumps(
                    {
                        "update": {
                            "_index": "ta_video",
                            "_id": video_id,
                        }
                    }
                ),
                json.dumps({"doc": {"media_url": resolved_media_url}}),
            ]
        )

    if not bulk_lines:
        stdout.write(style.SUCCESS("    no paths to repair"))
        return

    payload = "\n".join(bulk_lines) + "\n"
    response, status_code = ElasticWrap("_bulk?refresh=true").post(
        payload, ndjson=True
    )
    if status_code not in (200, 201) or response.get("errors"):
        stdout.write(style.ERROR("    failed to repair some media paths"))
        return

    repaired = len(bulk_lines) // 2
    stdout.write(style.SUCCESS(f"    ✓ repaired {repaired} media paths"))
