"""Regression tests for download queue cleanup behavior."""

from download.src import queue_interact


def test_delete_item_can_suppress_missing_queue_item_errors(monkeypatch):
    """
    Cleanup of an already-removed item must pass through print suppression.
    """
    calls = []

    class _ElasticWrap:
        def __init__(self, path):
            calls.append(("init", path))

        def delete(self, **kwargs):
            calls.append(("delete", kwargs))
            return {}, 404

    monkeypatch.setattr(queue_interact, "ElasticWrap", _ElasticWrap)

    queue_interact.PendingInteract("video").delete_item(print_error=False)

    assert calls == [
        ("init", "ta_download/_doc/video"),
        ("delete", {"refresh": True, "print_error": False}),
    ]
