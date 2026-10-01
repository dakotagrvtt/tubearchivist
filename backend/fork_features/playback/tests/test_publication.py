"""Publication races against real source and playback cache invalidation."""

import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from common.src.env_settings import EnvironmentSettings
from fork_features.playback import cache, hls, tasks


class _Connection:
    def __init__(self):
        self.locks = {}

    def set(self, key, token, **_kwargs):
        if key in self.locks:
            return False
        self.locks[key] = token
        return True

    def eval(self, _script, _count, key, token, *renew):
        if self.locks.get(key) != token:
            return 0
        if not renew:
            del self.locks[key]
        return 1


class _Redis:
    NAME_SPACE = "ta:"

    def __init__(self):
        self.conn = _Connection()
        self.statuses = {}

    def set_message(self, key, message, **_kwargs):
        self.statuses[key] = message

    def del_message(self, key):
        self.statuses.pop(key, None)


@pytest.fixture(params=["hls", "mp4"])
def worker(request, monkeypatch, tmp_path):
    """Execute worker publication with only ffmpeg/Redis boundaries faked."""
    kind = request.param
    module = hls if kind == "hls" else tasks
    redis = _Redis()
    source = tmp_path / "media" / "video.mkv"
    source.parent.mkdir()
    source.write_bytes(b"original archive")
    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(source.parent))
    monkeypatch.setattr(
        EnvironmentSettings, "CACHE_DIR", str(tmp_path / "cache")
    )
    for target in (hls, tasks):
        monkeypatch.setattr(target, "RedisArchivist", lambda: redis)
        monkeypatch.setattr(
            target, "AppConfig", lambda: SimpleNamespace(config={})
        )
        monkeypatch.setattr(target, "is_feature_enabled", lambda *_args: True)
    monkeypatch.setattr(cache, "RedisArchivist", lambda: redis)

    def ffmpeg(command, *_args):
        if kind == "hls":
            for output in command:
                if output.endswith("/index.m3u8"):
                    Path(output).write_bytes(b"#EXTM3U")
        else:
            Path(command[-1]).write_bytes(b"prepared media")
        return 0, True

    monkeypatch.setattr(tasks, "_run_ffmpeg_with_lease", ffmpeg)
    monkeypatch.setattr(hls, "_run_ffmpeg_with_lease", ffmpeg)
    output = Path(
        hls.hls_directory("video")
        if kind == "hls"
        else tasks.playback_cache_path("video")
    )
    neighboring = [
        tmp_path / "cache/transcode/neighbor.mp4",
        tmp_path / "cache/hls/neighbor/master.m3u8",
        tmp_path / "cache/hls/video.successor.part/keep",
    ]
    for path in neighboring:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"neighbor")

    def run():
        if kind == "hls":
            return hls.prepare_hls_playback.run(
                "video",
                source.name,
                [{"type": "audio", "index": 1}, {"type": "audio", "index": 2}],
            )
        return tasks.prepare_playback.run("video", source.name)

    return SimpleNamespace(
        kind=kind,
        module=module,
        source=source,
        output=output,
        redis=redis,
        status_key=f"{'hls' if kind == 'hls' else 'playback'}:video",
        run=run,
        neighboring=neighboring,
    )


def _change_source(worker, change):
    worker.source.unlink()
    if change == "replace":
        worker.source.write_bytes(b"replacement archive")


@pytest.mark.parametrize("change", ["delete", "replace"])
def test_source_change_after_precheck_cannot_survive_publication(
    worker, monkeypatch, change
):
    """Invalidate before publication, including MP4's complete/partial gap."""
    check_source = worker.module._source_changed
    replace = os.replace
    remove = os.remove
    changed = False
    published = False

    def source_changed(path, original_stat):
        nonlocal changed
        result = check_source(path, original_stat)
        if not changed:
            assert result is False
            changed = True
            _change_source(worker, change)
            if worker.kind == "hls":
                cache.invalidate_playback_cache("video")
        return result

    def remove_cache(path):
        nonlocal published
        if str(path) == str(worker.output) and not published:
            published = True
            try:
                remove(path)
            except FileNotFoundError:
                pass
            replace(f"{worker.output}.part.mp4", worker.output)
            return
        return remove(path)

    def publish_mp4(staged, output):
        monkeypatch.setattr(cache.os, "remove", remove_cache)
        cache.invalidate_playback_cache("video")

    monkeypatch.setattr(worker.module, "_source_changed", source_changed)
    if worker.kind == "mp4":
        monkeypatch.setattr(tasks.os, "replace", publish_mp4)

    result = worker.run()

    assert result == "stale-source"
    assert not worker.output.exists()
    assert worker.status_key not in worker.redis.statuses
    assert not worker.redis.conn.locks
    assert all(path.read_bytes() == b"neighbor" for path in worker.neighboring)


@pytest.mark.parametrize("change", ["delete", "replace"])
def test_source_change_during_ready_write_cannot_recreate_ready_status(
    worker, monkeypatch, change
):
    """A ready status write must be included in the final source check."""
    set_message = worker.redis.set_message

    def write_status(key, message, **kwargs):
        if message == {"status": "ready"}:
            _change_source(worker, change)
            cache.invalidate_playback_cache("video")
        set_message(key, message, **kwargs)

    monkeypatch.setattr(worker.redis, "set_message", write_status)

    assert worker.run() == "stale-source"
    assert not worker.output.exists()
    assert worker.status_key not in worker.redis.statuses
    assert not worker.redis.conn.locks


@pytest.mark.parametrize(
    ("replace_output", "lose_lease"),
    [(True, False), (True, True), (False, True)],
)
def test_stale_publication_preserves_successor_output_and_status(
    worker, monkeypatch, replace_output, lose_lease
):
    """Rollback must match the staging inode and respect successor leases."""
    set_message = worker.redis.set_message
    successor = worker.output.with_name(worker.output.name + ".successor")

    def write_status(key, message, **kwargs):
        set_message(key, message, **kwargs)
        if message == {"status": "ready"}:
            worker.source.unlink()
            if replace_output:
                # Allocate a separate inode before removing the old output.
                if worker.kind == "hls":
                    successor.mkdir()
                    (successor / "master.m3u8").write_bytes(b"successor")
                    shutil.rmtree(worker.output)
                else:
                    successor.write_bytes(b"successor")
                os.replace(successor, worker.output)
            else:
                artifact = (
                    worker.output / "master.m3u8"
                    if worker.kind == "hls"
                    else worker.output
                )
                artifact.write_bytes(b"successor")
            if lose_lease:
                for lock_key in worker.redis.conn.locks:
                    worker.redis.conn.locks[lock_key] = "successor-owner"
            set_message(key, {"status": "preparing", "owner": "successor"})

    monkeypatch.setattr(worker.redis, "set_message", write_status)

    assert worker.run() == "lock-lost"
    artifact = (
        worker.output / "master.m3u8"
        if worker.kind == "hls"
        else worker.output
    )
    assert artifact.read_bytes() == b"successor"
    assert worker.redis.statuses[worker.status_key] == {
        "status": "preparing",
        "owner": "successor",
    }
    if lose_lease:
        assert set(worker.redis.conn.locks.values()) == {"successor-owner"}


def test_deletion_after_final_check_removes_published_output(
    worker, monkeypatch
):
    """Once publication is complete, ordinary invalidation owns cleanup."""
    check_source = worker.module._source_changed
    checks = 0

    def source_changed(path, original_stat):
        nonlocal checks
        result = check_source(path, original_stat)
        checks += 1
        if checks == 2:
            assert result is False
            worker.source.unlink()
            cache.invalidate_playback_cache("video")
        return result

    monkeypatch.setattr(hls, "_source_changed", source_changed)
    monkeypatch.setattr(tasks, "_source_changed", source_changed)

    assert worker.run() == "ready"
    assert not worker.output.exists()
    assert worker.status_key not in worker.redis.statuses
    assert not worker.redis.conn.locks


def test_unchanged_source_keeps_complete_publication(worker):
    """The final source check preserves a successfully prepared artifact."""
    assert worker.run() == "ready"
    artifact = (
        worker.output / "master.m3u8"
        if worker.kind == "hls"
        else worker.output
    )
    assert artifact.stat().st_size > 0
    assert worker.redis.statuses[worker.status_key] == {"status": "ready"}
    assert not worker.redis.conn.locks
