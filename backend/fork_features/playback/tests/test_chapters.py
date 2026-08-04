from fork_features.playback.chapters import normalize_chapters


def test_normalize_chapters_sorts_and_uses_next_start():
    chapters = normalize_chapters(
        [
            {"start_time": 30, "title": "Second"},
            {"start_time": 0, "end_time": 20, "title": "First"},
        ],
        duration=60,
    )

    assert chapters == [
        {"start": 0.0, "end": 20.0, "title": "First"},
        {"start": 30.0, "end": 60.0, "title": "Second"},
    ]


def test_normalize_chapters_discards_invalid_ranges():
    chapters = normalize_chapters(
        [
            {"start_time": -5, "end_time": 0, "title": "empty"},
            {"start_time": "bad", "end_time": 10, "title": "bad"},
            {"start_time": 10, "end_time": 5, "title": "backwards"},
        ],
        duration=30,
    )

    assert chapters == []


def test_normalize_chapters_missing_duration_is_safe():
    assert normalize_chapters([{"start_time": 1, "end_time": 3}]) == [
        {"start": 1.0, "end": 3.0, "title": "Chapter 1"}
    ]
