import subprocess
from pathlib import Path
from types import SimpleNamespace

from common.src.env_settings import EnvironmentSettings
from fork_features.playback import hls


def test_build_hls_command_maps_each_audio_stream():
    command = hls.build_hls_command(
        "/youtube/video.mkv",
        "/cache/hls/video.part",
        [
            {"index": 1, "language": "en", "title": "English"},
            {"index": 3, "language": "es", "title": "Español"},
        ],
    )

    assert "-map" in command
    assert command[command.index("-map") + 1] == "0:v:0"
    assert "0:1" in command
    assert "0:3" in command
    assert "-an" in command
    assert command[-1].endswith("audio1/index.m3u8")


def test_master_playlist_makes_duplicate_audio_names_unique(tmp_path):
    hls.write_master_playlist(
        str(tmp_path),
        [
            {"language": "en", "title": "English"},
            {"language": "en", "title": "English"},
            {"language": "en", "title": "English 1"},
            {"language": "en", "title": "English"},
            {"language": "ja", "title": "Japanese"},
        ],
    )

    playlist = (tmp_path / "master.m3u8").read_text()
    names = [
        line.split('NAME="', 1)[1].split('"', 1)[0]
        for line in playlist.splitlines()
        if line.startswith("#EXT-X-MEDIA:")
    ]
    assert names == [
        "English",
        "English 2",
        "English 1",
        "English 3",
        "Japanese",
    ]
    assert len(names) == len(set(names))


def test_hls_task_disabled_clears_status(monkeypatch):
    class Redis:
        def __init__(self):
            self.deleted = []

        def del_message(self, key):
            self.deleted.append(key)

    redis = Redis()
    monkeypatch.setattr(hls, "RedisArchivist", lambda: redis)
    monkeypatch.setattr(
        hls,
        "AppConfig",
        lambda: type("Config", (), {"config": {"application": {}}})(),
    )
    monkeypatch.setattr(hls, "is_feature_enabled", lambda *_args: False)

    assert hls.prepare_hls_playback.run("video", "video.mkv", []) == "disabled"
    assert redis.deleted == ["hls:video"]


def test_hls_cache_ready_requires_master_file(monkeypatch, tmp_path):
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(tmp_path))
    assert not hls.hls_cache_ready("video")
    master = Path(hls.hls_master_path("video"))
    master.parent.mkdir(parents=True)
    master.write_text("#EXTM3U")
    assert hls.hls_cache_ready("video")


def test_hls_task_enforces_cache_limits_after_generation(
    monkeypatch, tmp_path
):
    class Connection:
        @staticmethod
        def set(*_args, **_kwargs):
            return True

        @staticmethod
        def eval(*_args, **_kwargs):
            return 1

    class Redis:
        NAME_SPACE = "ta:"

        def __init__(self):
            self.conn = Connection()
            self.messages = []

        def set_message(self, key, message, expire=None):
            self.messages.append((key, message, expire))

    redis = Redis()
    media = tmp_path / "media"
    cache = tmp_path / "cache"
    source = media / "channel" / "video.mkv"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    cleanup_calls = []

    def run_ffmpeg(command, *_args):
        output = Path(command[command.index("-hls_segment_filename") + 2])
        output.write_text("#EXTM3U")
        return 0, True

    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(media))
    monkeypatch.setattr(EnvironmentSettings, "CACHE_DIR", str(cache))
    monkeypatch.setattr(hls, "RedisArchivist", lambda: redis)
    monkeypatch.setattr(
        hls,
        "AppConfig",
        lambda: type("Config", (), {"config": {"application": {}}})(),
    )
    monkeypatch.setattr(hls, "is_feature_enabled", lambda *_args: True)
    monkeypatch.setattr(hls, "_run_ffmpeg_with_lease", run_ffmpeg)
    monkeypatch.setattr(
        hls, "cleanup_hls_cache", lambda: cleanup_calls.append(True)
    )

    result = hls.prepare_hls_playback.run(
        "video",
        "channel/video.mkv",
        [
            {"type": "audio", "index": 1, "language": "en"},
            {"type": "audio", "index": 2, "language": "es"},
        ],
    )

    assert result == "ready"
    assert cleanup_calls == [True]
    assert redis.messages[-1][1] == {"status": "ready"}


def test_video_tasks_reexports_hls_task_for_celery_discovery():
    from video import tasks as video_tasks

    assert video_tasks.prepare_hls_playback is hls.prepare_hls_playback


class _LeaseConnection:
    """Model Redis owner checks and expiry against the ffmpeg clock."""

    def __init__(self):
        self.now = 0
        self.token = None
        self.expires = 0
        self.duplicate_allowed = False

    def set(self, _key, token, nx, ex):
        if nx and self.token is not None and self.now < self.expires:
            return False
        self.token = token
        self.expires = self.now + ex
        return True

    def eval(self, script, _num_keys, _key, token, *args):
        if self.now >= self.expires or self.token != token:
            return 0
        if args:
            self.expires = self.now + args[0]
        else:
            self.token = None
        return 1


class _LeaseRedis:
    NAME_SPACE = "ta:"

    def __init__(self):
        self.conn = _LeaseConnection()
        self.messages = []

    def set_message(self, key, message, expire=None):
        self.messages.append((key, message, expire))


class _FFmpegProcess:
    returncode = None
    terminated = False
    killed = False
    reaped = False

    def __init__(self, command, redis, duration, finish, tick):
        self.command = command
        self.redis = redis
        self.finish = finish
        self.tick = tick
        self.remaining = duration
        self.output = Path(
            command[command.index("-hls_segment_filename") + 2]
        ).parent.parent

    def wait(self, timeout=None):
        if self.terminated or self.killed:
            self.returncode = -9 if self.killed else -15
            self.reaped = True
            return self.returncode
        elapsed = min(timeout or self.remaining, self.remaining)
        self.redis.conn.now += elapsed
        self.remaining -= elapsed
        if self.redis.conn.now >= self.redis.conn.expires:
            self.redis.conn.duplicate_allowed = True
        if self.tick:
            self.tick(self.redis, self)
        if self.remaining:
            raise subprocess.TimeoutExpired(self.command, timeout)
        (self.output / "video" / "index.m3u8").write_text("#EXTM3U")
        for audio_dir in self.output.glob("audio*"):
            (audio_dir / "index.m3u8").write_text("#EXTM3U")
        self.returncode = 0
        self.reaped = True
        if self.finish:
            self.finish(self.redis, self)
        return self.returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def _hls_worker(monkeypatch, tmp_path, duration=0, finish=None, tick=None):
    """Use real cache files while simulating ffmpeg and Redis timing."""
    from fork_features.playback import tasks

    redis = _LeaseRedis()
    source = tmp_path / "media" / "video.mkv"
    source.parent.mkdir()
    source.write_bytes(b"archived source")
    monkeypatch.setattr(EnvironmentSettings, "MEDIA_DIR", str(source.parent))
    monkeypatch.setattr(
        EnvironmentSettings, "CACHE_DIR", str(tmp_path / "cache")
    )
    monkeypatch.setattr(hls, "RedisArchivist", lambda: redis)
    monkeypatch.setattr(hls, "AppConfig", lambda: SimpleNamespace(config={}))
    monkeypatch.setattr(hls, "is_feature_enabled", lambda *_args: True)
    monkeypatch.setattr(hls, "cleanup_hls_cache", lambda: None)
    processes = []

    def popen(command, **_kwargs):
        process = _FFmpegProcess(command, redis, duration, finish, tick)
        processes.append(process)
        return process

    def run(command, **kwargs):
        process = popen(command, **kwargs)
        process.wait()
        return process

    monkeypatch.setattr(tasks.subprocess, "Popen", popen)
    monkeypatch.setattr(tasks.subprocess, "run", run)
    streams = [
        {"type": "audio", "index": 1, "language": "en"},
        {"type": "audio", "index": 2, "language": "es"},
    ]
    return redis, source, processes, streams


def test_hls_renews_lease_beyond_original_ttl(monkeypatch, tmp_path):
    redis, source, processes, streams = _hls_worker(
        monkeypatch, tmp_path, duration=7500
    )

    result = hls.prepare_hls_playback.run("video", source.name, streams)

    assert not redis.conn.duplicate_allowed
    assert result == "ready"
    assert processes[0].reaped
    assert hls.hls_cache_ready("video")
    assert source.read_bytes() == b"archived source"
    assert redis.conn.token is None
    assert not list((tmp_path / "cache" / "hls").glob("*.part"))


def test_hls_lease_loss_stops_worker_and_preserves_successor(
    monkeypatch, tmp_path
):
    successor_dir = tmp_path / "cache" / "hls" / "video.successor.part"
    output_dir = tmp_path / "cache" / "hls" / "video"

    def lose_lease(redis, _process):
        redis.conn.token = "successor"
        successor_dir.mkdir(parents=True, exist_ok=True)
        (successor_dir / "keep").write_text("successor temporary data")
        output_dir.mkdir(exist_ok=True)
        (output_dir / "master.m3u8").write_text("successor presentation")
        redis.set_message("hls:video", {"status": "preparing"})

    redis, source, processes, streams = _hls_worker(
        monkeypatch, tmp_path, duration=7500, tick=lose_lease
    )

    result = hls.prepare_hls_playback.run("video", source.name, streams)

    assert result == "lock-lost"
    assert processes[0].terminated and processes[0].reaped
    assert (successor_dir / "keep").read_text() == "successor temporary data"
    assert (output_dir / "master.m3u8").read_text() == "successor presentation"
    assert redis.conn.token == "successor"
    assert redis.messages[-1][1] == {"status": "preparing"}
    assert not processes[0].output.exists()


def test_hls_checks_owner_before_publication(monkeypatch, tmp_path):
    def lose_lease(redis, _process):
        redis.conn.token = "successor"
        redis.set_message("hls:video", {"status": "pending"})

    redis, source, processes, streams = _hls_worker(
        monkeypatch, tmp_path, finish=lose_lease
    )

    result = hls.prepare_hls_playback.run("video", source.name, streams)

    assert result == "lock-lost"
    assert not hls.hls_cache_ready("video")
    assert not processes[0].output.exists()
    assert redis.conn.token == "successor"
    assert redis.messages[-1][1] == {"status": "pending"}


def test_hls_rejects_changed_archive(monkeypatch, tmp_path):
    def replace_source(_redis, _process):
        source.write_bytes(b"replacement archived source")

    redis, source, processes, streams = _hls_worker(
        monkeypatch, tmp_path, finish=replace_source
    )

    result = hls.prepare_hls_playback.run("video", source.name, streams)

    assert result == "stale-source"
    assert not hls.hls_cache_ready("video")
    assert not processes[0].output.exists()
    assert source.read_bytes() == b"replacement archived source"
    assert redis.messages[-1][1] == {"status": "pending"}


def test_hls_staging_does_not_remove_another_workers_artifacts(
    monkeypatch, tmp_path
):
    _redis, source, processes, streams = _hls_worker(monkeypatch, tmp_path)
    foreign = tmp_path / "cache" / "hls" / "video.part"
    foreign.mkdir(parents=True)
    (foreign / "keep").write_text("another worker")

    assert (
        hls.prepare_hls_playback.run("video", source.name, streams) == "ready"
    )

    assert (foreign / "keep").read_text() == "another worker"
    assert processes[0].output != foreign
    assert not processes[0].output.exists()


def test_failed_hls_removes_only_own_staging(monkeypatch, tmp_path):
    def fail(_redis, process):
        process.returncode = 1

    redis, source, processes, streams = _hls_worker(
        monkeypatch, tmp_path, finish=fail
    )
    foreign = tmp_path / "cache" / "hls" / "video.other.part"
    foreign.mkdir(parents=True)
    (foreign / "keep").write_text("another worker")

    assert (
        hls.prepare_hls_playback.run("video", source.name, streams) == "failed"
    )

    assert (foreign / "keep").read_text() == "another worker"
    assert not processes[0].output.exists()
    assert not hls.hls_cache_ready("video")
    assert redis.messages[-1][1]["status"] == "failed"
    assert redis.conn.token is None


def test_hls_ffmpeg_launch_error_cleans_up_and_releases_lock(
    monkeypatch, tmp_path
):
    from fork_features.playback import tasks

    redis, source, _processes, streams = _hls_worker(monkeypatch, tmp_path)

    def fail_launch(*_args, **_kwargs):
        raise OSError("ffmpeg unavailable")

    monkeypatch.setattr(tasks.subprocess, "Popen", fail_launch)

    assert (
        hls.prepare_hls_playback.run("video", source.name, streams) == "failed"
    )

    assert not list((tmp_path / "cache" / "hls").iterdir())
    assert redis.messages[-1][1] == {
        "status": "failed",
        "error": "ffmpeg unavailable",
    }
    assert redis.conn.token is None


def test_hls_owned_lock_excludes_second_worker(monkeypatch, tmp_path):
    redis, source, processes, streams = _hls_worker(monkeypatch, tmp_path)
    redis.conn.set("ta:hls:video:lock", "first-worker", nx=True, ex=3600)

    assert (
        hls.prepare_hls_playback.run("video", source.name, streams)
        == "already-running"
    )

    assert not processes
    assert redis.conn.token == "first-worker"
    assert not redis.messages
