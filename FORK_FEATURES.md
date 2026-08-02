# Fork features

This fork keeps optional behavior behind explicit integration points. The
current feature set is audio-track archiving; generic URL downloads and the
old Python range streamer are intentionally removed.

## Layout

```text
backend/fork_features/
  apps.py                 Django loader
  registry.py             validated contribution registry
  audio_tracks/           language discovery, download hook, muxing, metadata
frontend/src/fork_features/
  registry.ts             settings and stream-label registries
  audioTracks/             feature-owned settings UI and labels
```

`fork_features.apps.ForkFeaturesConfig` imports each enabled backend feature
once at Django startup. A feature registers only the contributions it owns:

```python
register(
    feature_id="audio_tracks",
    config_defaults={"audio_multistreams": False, "audio_languages": None},
    app_serializer_fields={...},
    channel_serializer_fields={...},
    channel_overwrite_keys=["audio_multistreams", "audio_languages"],
    download_hook=AudioTracksDownloadHook(),
    media_stream_enricher=AudioTracksMediaStreamEnricher(),
)
```

The registry rejects duplicate feature IDs and duplicate contribution keys.
Core code consumes these accessors at configuration, serializer, channel
overwrite, download, and media-stream boundaries; it does not import feature
implementation details.

## Audio-track behavior

When `audio_multistreams` is enabled, the hook first performs a normal primary
download using the effective user/channel format and container. It then
downloads requested or discovered additional languages into a private
temporary directory and asks ffmpeg to append them. If discovery, an extra
download, or muxing fails, the primary file is left untouched and archived.
This is deliberately silent best-effort behavior.

`audio_languages` accepts comma-separated BCP-47-style values (`en`, `es-419`,
`zh-Hans`). Values are normalized and deduplicated. An empty value means
auto-discover all available languages. The primary stream remains the normal
effective yt-dlp download; every selected/discovered language is downloaded as
an additional stream. If the primary already contains one of those languages,
the resulting file may contain a duplicate track, but the primary stream stays
first and playback remains deterministic.

The feature never forces MKV, replaces the configured format, or enables
yt-dlp's multistream selector. The output extension stays aligned with the
effective container. ffmpeg metadata enrichment exposes language, title,
channel count, and layout to the existing stream serializer.

## Playback preparation

The `/api/video/<id>/stream/` endpoint serves MP4 files through an internal
Nginx `X-Accel-Redirect`. Other containers return `202` and enqueue the
`prepare_playback` Celery task. Redis records `pending`, `preparing`, `ready`,
or `failed` state and a per-video lock prevents duplicate ffmpeg work. The
status endpoint is `/api/video/<id>/stream/status/`. Nginx serves completed
files from internal range-capable locations; request-time Django ffmpeg and
the global asyncio monkey patch are gone.

## Configuration ownership and migration

Audio keys are registered by the feature, not duplicated in core config or
serializer declarations. Startup merges feature defaults before adding or
removing keys. A one-time migration copies the old singular application key
`audio_multistream` to `audio_multistreams`, and an Elasticsearch migration
does the same for channel overwrites without discarding values.

## Adding another feature

1. Add `backend/fork_features/<name>/__init__.py` and call `register()`.
2. Import it in `ForkFeaturesConfig.ready()`.
3. Keep frontend components under `frontend/src/fork_features/<name>/` and add
   them to the appropriate registry arrays.
4. Add focused tests for registry collisions and each integration boundary.

Do not add generic URL resolvers, source-URL fields, request-time media
transcoders, or duplicate settings controls. If a feature needs a new core
boundary, document and test that boundary here first.

## Removed fork features

`generic_downloads` was removed because it made YouTube-specific queue,
identity, channel, metadata, and security assumptions ambiguous while its
resolver was not consistently registered. Existing Elasticsearch documents
are not deleted automatically; they remain available for inspection or manual
cleanup, but new queue and playback flows only support native YouTube data.

The old `streaming.py` helper and `quiet_asyncio` loop patch were removed in
favor of the asynchronous playback path above.
