"""Tests for playback startup data repair."""

import json

from common.src.env_settings import EnvironmentSettings
from fork_features.playback import migrations


class _Output:
    def __init__(self):
        self.messages = []

    def write(self, message):
        self.messages.append(message)


class _Style:
    SUCCESS = staticmethod(str)
    ERROR = staticmethod(str)


def test_repair_legacy_mkv_path(monkeypatch, tmp_path):
    """Bulk-update an indexed MKV when its archived MP4 exists."""
    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(tmp_path))
    media_dir = tmp_path / "channel"
    media_dir.mkdir()
    (media_dir / "video.mp4").write_bytes(b"video")

    class FakePaginate:
        def __init__(self, index_name, data):
            assert index_name == "ta_video"
            assert data["query"]["wildcard"]["media_url"]["value"] == ("*.mkv")

        @staticmethod
        def get_results():
            return [
                {
                    "youtube_id": "video",
                    "media_url": "channel/video.mkv",
                }
            ]

    posted = {}

    class FakeElastic:
        def __init__(self, path):
            assert path == "_bulk?refresh=true"

        @staticmethod
        def post(payload, ndjson=False):
            posted["payload"] = payload
            posted["ndjson"] = ndjson
            return {"errors": False}, 200

    monkeypatch.setattr(migrations, "IndexPaginate", FakePaginate)
    monkeypatch.setattr(migrations, "ElasticWrap", FakeElastic)

    output = _Output()
    migrations.repair_legacy_media_paths(output, _Style())

    lines = posted["payload"].splitlines()
    assert posted["ndjson"] is True
    assert json.loads(lines[0]) == {
        "update": {"_index": "ta_video", "_id": "video"}
    }
    assert json.loads(lines[1]) == {"doc": {"media_url": "channel/video.mp4"}}
    assert output.messages[-1] == "    ✓ repaired 1 media paths"
