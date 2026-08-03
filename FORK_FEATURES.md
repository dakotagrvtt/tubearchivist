# Fork features

This fork contains two kinds of additions:

- **Optional extensions** contribute settings or lifecycle behavior through the
  fork registries. Audio-track archiving is currently the only optional
  extension.
- **Fork infrastructure** replaces or augments an upstream workflow and is
  always active. Asynchronous, range-capable playback is fork infrastructure;
  it is not a registry-enabled option.

Generic URL downloads, the Python range streamer, and the global asyncio patch
are intentionally removed.

## Source-change rule

Substantial fork behavior must live under `backend/fork_features/` or
`frontend/src/fork_features/`. Upstream-owned files may contain only the
smallest framework-required import, dispatch, type, route, or render hook. Do
not move feature algorithms, migrations, cleanup, task implementation, or UI
sections into core files.

When a new core boundary is unavoidable:

1. Define a narrow feature-owned interface.
2. Add the smallest possible call site in core.
3. Test the feature implementation and the integration boundary.
4. Document the hook in the table below before merging.

## Layout and loading

```text
backend/fork_features/
  apps.py                 loads self-registering optional extensions
  registry.py             validates extension contributions
  startup.py              single startup/config integration surface
  audio_tracks/           settings, discovery, download, mux, migrations
  playback/               paths, request handling, task, repair, cleanup
frontend/src/fork_features/
  registry.ts             feature-owned UI and stream-label slots
  audioTracks/            audio settings UI and labels
  playback/               playback preparation hook and status UI
```

`ForkFeaturesConfig.ready()` imports optional extensions whose package-level
`register()` call contributes configuration defaults, serializer fields,
channel overwrite keys, download hooks, or media-stream enrichers. The registry
rejects duplicate feature IDs and conflicting contribution keys. Fork
infrastructure such as playback is imported only by its required framework
hooks and does not call `register()`.

## Core integration boundaries

| Area | Thin core responsibility | Feature-owned implementation |
| --- | --- | --- |
| Django loading | Install `fork_features` | `apps.py`, `registry.py` |
| Configuration/schema | Merge registered defaults/fields and map stored keys | audio registration and ES mapping |
| Downloads/media metadata | Invoke registered hooks | `audio_tracks/` |
| Settings UI | Render registered sections/labels | frontend registry and `audioTracks/` |
| Startup | Call config migrations, cleanup, and data repairs | `fork_features/startup.py` |
| Playback API | Route endpoints and delegate the view | `playback/views.py` |
| Celery discovery | Re-export `prepare_playback` | `playback/tasks.py` |
| Archive replacement | Call cache invalidation | `playback/cache.py` |
| Browser playback | Call the preparation hook and render status | `frontend/src/fork_features/playback/` |
| Range serving | Provide internal Nginx locations | protected media/transcode locations |

## Audio-track behavior

When `audio_multistreams` is enabled, the normal primary download retains the
effective user or channel format and container. The post-download hook attempts
to stage each explicitly requested language for which yt-dlp exposes a usable
DASH or HLS format. With no explicit languages, it discovers available tracks;
a single discovered language is skipped because the primary already supplies
it. Individual extraction/download failures and incompatible container codecs
leave the primary download untouched and do not block archival.

`audio_languages` accepts comma-separated BCP-47-style values such as `en`,
`es-419`, and `zh-Hans`. Values are normalized and deduplicated. An empty value
enables discovery. Appended tracks receive language and title metadata, while
the primary stream remains first. The feature does not force MKV, replace the
configured format, or enable yt-dlp's multistream selector.

Staging uses private `ta-audio-*` temporary directories. Normal completion
removes them in `finally`; startup cleanup reclaims directories left by an
interrupted worker.

## Playback preparation

`/api/video/<id>/stream/` authorizes and serves archived MP4 files through an
internal Nginx `X-Accel-Redirect`. Other source containers return `202`, enqueue
the `prepare_playback` Celery task, and are transcoded to a persistent MP4 cache.
The status endpoint is `/api/video/<id>/stream/status/`.

Redis records `pending`, `preparing`, `ready`, or `failed`. An ownership-token
lock is renewed throughout ffmpeg execution and released only by its owner.
Completed cache files are authoritative even after Redis expiry or restart.
Startup removes request-scoped Redis state but preserves completed transcodes.
Both original and prepared files are served by internal, range-capable Nginx
locations rather than through Django.

## Idempotent startup repairs

Feature repairs run even when the release-wide migration skip flag is set:

- Audio config repair copies `audio_multistream` to `audio_multistreams` before
  core removes obsolete keys. The channel repair performs the equivalent
  Elasticsearch update without overwriting an existing plural value.
- Playback repair resolves stale indexed `.mkv` paths when the corresponding
  archived media exists under another supported extension.

These are retry-safe startup repairs, not version-marker migrations. Their
queries become no-ops after the stored data is corrected.

## Adding an optional extension

1. Create `backend/fork_features/<name>/` and call `register()` from its
   `__init__.py`.
2. Import that package in `ForkFeaturesConfig.ready()`.
3. Put frontend sections under `frontend/src/fork_features/<name>/` and add
   them to the relevant frontend registry list.
4. Put migrations and cleanup in the feature package and expose them through
   `fork_features/startup.py`.
5. Add tests for registration collisions, success, partial failure, cleanup,
   and every new core boundary.

Do not add generic URL resolvers, source-URL fields, request-time transcoders,
duplicate settings controls, or feature-specific algorithms to upstream-owned
modules.
