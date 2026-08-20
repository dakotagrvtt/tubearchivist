"""Regression tests for filesystem queue cleanup behavior."""

from appsettings.src import filesystem
from download.src import queue_interact


def test_filesystem_cleanup_suppresses_missing_queue_item_errors(monkeypatch):
    """Scanner cleanup must delete a queue item without printing a 404."""
    calls = []

    class _ElasticWrap:
        def __init__(self, path):
            calls.append(("init", path))

        def delete(self, **kwargs):
            calls.append(("delete", kwargs))
            return {}, 404

    monkeypatch.setattr(queue_interact, "ElasticWrap", _ElasticWrap)

    filesystem.Scanner._cleanup("video")

    assert calls == [
        ("init", "ta_download/_doc/video"),
        ("delete", {"refresh": True, "print_error": False}),
    ]
