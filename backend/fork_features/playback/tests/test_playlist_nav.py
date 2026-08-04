from fork_features.playback.playlist_nav import PlaylistNavEnricher


def test_playlist_nav_enricher_exposes_downloaded_order_only():
    nav = {"playlist_meta": {"playlist_id": "playlist"}}
    playlist = {
        "playlist_entries": [
            {
                "youtube_id": "one",
                "title": "One",
                "uploader": "uploader",
                "idx": 0,
                "downloaded": True,
            },
            {
                "youtube_id": "two",
                "title": "Two",
                "uploader": None,
                "idx": 1,
                "downloaded": False,
            },
        ]
    }

    assert PlaylistNavEnricher().enrich_nav(nav, playlist)[
        "playlist_entries"
    ] == [
        {
            "youtube_id": "one",
            "title": "One",
            "uploader": "uploader",
            "idx": 0,
            "downloaded": True,
        }
    ]
