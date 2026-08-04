# Fork features

This fork contains two kinds of additions:

- **Optional extensions** contribute settings or lifecycle behavior through the
  fork registries. Audio-track archiving is currently the only optional
  extension.
- **Fork infrastructure** replaces or augments an upstream workflow. Enhanced
  playback and the Vidstack player are registered as default-on features and
  can be disabled independently from Application Settings.

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
  types.ts                feature-owned application settings types
  audioTracks/            audio settings UI and labels
  playback/               playback preparation, Vidstack surface, hooks, and status UI
```

`ForkFeaturesConfig.ready()` imports optional extensions whose package-level
`register()` call contributes configuration defaults, serializer fields,
channel overwrite keys, download hooks, or media-stream enrichers. The registry
rejects duplicate feature IDs and conflicting contribution keys. Fork
infrastructure uses the same registration boundary when it needs an
application-level master switch. Missing switches resolve to their registered
default so older configurations remain enabled during startup synchronization.

## Feature switches

Users can manage fork features from **Settings → Application → Fork Features**.
All switches are enabled by default.

| Setting | When enabled | When disabled |
| --- | --- | --- |
| Audio Tracks | Allows the Download Format and per-channel multistream settings to archive additional audio languages. | Stops additional-track downloads and hides their configuration controls. Existing multistream settings and archived tracks are preserved. |
| Enhanced Playback | Serves MP4 files with range support and prepares non-MP4 files for browser playback. | Uses the original media URL directly and starts no new preparation tasks. Browser-incompatible containers such as MKV may not play. |
| Enhanced Player | Uses the fork's Vidstack controls, chapter labels, subtitles, Picture-in-Picture, progress hooks, playlist controls, and mobile gestures. | Uses the native browser player while retaining Enhanced Playback media preparation. |
| Multi-Audio Playback | Builds a cached HLS presentation with the archived audio streams as selectable renditions and one video rendition. | Uses the normal direct or prepared media source; no HLS cache is created. |

Changes apply to new requests and jobs immediately. A player open in another
browser session falls back to the direct media URL when the server reports that
Enhanced Playback was disabled. A download or transcode already running may
finish. Disabling a switch never deletes archived media, metadata, saved
settings, or completed playback caches.

The stored configuration keys are
`application.enable_fork_audio_tracks`, `application.enable_fork_playback`,
`application.enable_fork_player`, and
`application.enable_fork_multi_audio_playback`. The Audio Tracks master switch takes
precedence over global and per-channel `audio_multistreams` values.

## Core integration boundaries

| Area | Thin core responsibility | Feature-owned implementation |
| --- | --- | --- |
| Django loading | Install `fork_features` | `apps.py`, `registry.py` |
| Configuration/schema | Merge registered defaults/fields and map stored keys | audio registration and ES mapping |
| Downloads/media metadata | Invoke registered hooks | `audio_tracks/`, `playback/chapters.py` |
| Settings UI | Render registered sections/labels | frontend registry and `audioTracks/` |
| Startup | Call config migrations, cleanup, and data repairs | `fork_features/startup.py` |
| Playlist navigation | Invoke registered navigation enrichers | `playback/playlist_nav.py` |
| Playback API | Route endpoints and delegate the view | `playback/views.py`, `playback/hls.py` |
| Celery discovery | Re-export playback preparation tasks | `playback/tasks.py`, `playback/hls.py` |
| Archive replacement | Call cache invalidation | `playback/cache.py` |
| Browser playback | Expose the native player through one render hook | Player orchestration, preparation, controls, and lifecycle hooks under `frontend/src/fork_features/playback/` |
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

When enabled, `/api/video/<id>/stream/` authorizes and serves archived MP4 files
through an internal Nginx `X-Accel-Redirect`. Other source containers return
`202`, enqueue the `prepare_playback` Celery task, and are transcoded to a
persistent MP4 cache. The status endpoint is
`/api/video/<id>/stream/status/`. When disabled, those fork endpoints return a
feature-disabled error and the frontend uses the normal `/media/` URL.

Redis records `pending`, `preparing`, `ready`, or `failed`. An ownership-token
lock is renewed throughout ffmpeg execution and released only by its owner.
Completed cache files are authoritative even after Redis expiry or restart.
Startup removes request-scoped Redis state but preserves completed transcodes.
Both original and prepared files are served by internal, range-capable Nginx
locations rather than through Django.

## Enhanced player additions

Chapter labels are indexed from yt-dlp metadata and supplied to Vidstack as an
in-memory WebVTT track. No chapter thumbnails, image sprites, transcript panel,
or quality selector is generated. Playlist previous/next, autoplay, repeat, and
shuffle state is kept in the browser and remains unavailable when the Enhanced
Player switch is disabled. Mobile double-tap seek and vertical volume or player
brightness gestures can be configured below the player.

When Multi-Audio Playback is enabled and a video has multiple archived audio
streams, the backend creates one cached HLS video presentation with alternate
audio renditions. The cache contains one video playlist plus derived audio
playlists; it does not download another source video or quality. The cache is
removed when the source archive is replaced and is served only through protected
Nginx locations. If preparation or browser HLS playback fails, Vidstack retries
the existing direct media source without disabling the player for the session.
Completed HLS jobs enforce the cache age and size limits so a running service
does not depend on a restart to reclaim old presentations.

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
