# Fork Features – Maintainer Guide

This document explains how custom features that diverge from upstream
[TubeArchivist](https://github.com/tubearchivist/tubearchivist) are structured so that:

1. **Upstream merges stay clean** — fork-only code lives in isolated directories and is hooked
   into upstream files with the smallest possible diff.
2. **New features are easy to add** — drop a new module, call `register()` in the registry; no
   surgery on upstream page components required.
3. **Features can be toggled off** — removing the backend feature import and frontend registry
   entry disables the feature without deleting its code.

For branch and release workflow, see [BRANCHING.md](./BRANCHING.md).

---

## Directory Layout

```
backend/
└── fork_features/               ← Python package, isolated from upstream apps
    ├── __init__.py              ← Package marker / documentation
    ├── apps.py                  ← Django AppConfig (listed in INSTALLED_APPS)
    ├── registry.py              ← Central registry: register() + accessor functions
    └── audio_tracks/            ← "Multi-audio language download" feature
        ├── __init__.py          ← Calls registry.register() with feature hooks
        ├── languages.py         ← ISO language helpers
        ├── media_streams.py     ← Audio stream metadata enrichment for player UI
        ├── ffmpeg_merge.py      ← Post-download ffmpeg muxing logic
        └── downloader.py        ← DownloadHook implementation (pre/post download)

frontend/
└── src/fork_features/           ← TypeScript/React, isolated from upstream components
    ├── registry.ts              ← Exports APP_SETTINGS_SECTIONS, CHANNEL_SETTINGS_SECTIONS
    └── audioTracks/
        ├── AudioLanguageSelector.tsx
        ├── ApplicationSettingsSection.tsx
        └── ChannelSettingsSection.tsx
        └── streamLabels.ts      ← Audio stream label formatter for Video page
```

---

## How the Hook System Works

### Backend – Registry (`backend/fork_features/registry.py`)

Features register themselves by calling `register()` with any combination of hooks:

```python
from fork_features.registry import register

register(
    feature_id="audio_tracks",
    config_defaults={"audio_multistreams": False, "audio_languages": None},
    app_serializer_fields={"audio_multistreams": ..., "audio_languages": ...},
    channel_serializer_fields={"audio_multistreams": ..., "audio_languages": ...},
    channel_overwrite_keys=["audio_multistreams", "audio_languages"],
    download_hook=AudioTracksDownloadHook(),
    media_stream_enricher=AudioTracksMediaStreamEnricher(),
)
```

The registry exposes **accessor functions** that upstream integration points call:

| Accessor | Called from | Purpose |
|---|---|---|
| `get_config_defaults()` | `appsettings/src/config.py` → `_effective_defaults()` | Adds default values to `AppConfig.CONFIG_DEFAULTS["downloads"]` |
| `get_app_serializer_fields()` | `appsettings/serializers.py` → `AppConfigDownloadsSerializer.get_fields()` | Adds DRF fields to the downloads config serializer |
| `get_channel_serializer_fields()` | `channel/serializers.py` → `ChannelOverwriteSerializer.get_fields()` | Adds DRF fields to the channel overwrite serializer |
| `get_channel_overwrite_keys()` | `channel/src/index.py` → `YoutubeChannel.OVERWRITES` | Adds keys to the channel overwrite index list |
| `get_download_hooks()` | `download/src/yt_dlp_handler.py` → `_dl_single_vid()` | Returns `DownloadHook` objects called before/after each download |
| `get_url_resolvers()` | `common/src/urlparser.py` → `Parser.process_url()` | Returns `UrlResolver` objects consulted for non-YouTube URLs |
| `get_media_stream_enrichers()` | `video/src/media_streams.py` → `_extract_audio_metadata()` | Enriches extracted stream metadata for fork-specific UI |
| `get_channel_fallback_enrichers()` | `channel/src/index.py` → `_video_fallback()` | Enriches minimal channel docs built from video metadata (e.g. adds `channel_source_url`) |

Each upstream file contains a small, explicit integration point. The goal is to keep upstream
diffs narrow and predictable, even if a given file needs slightly more than 1-3 added lines.

### Backend – URL Resolvers

URL resolvers implement the `UrlResolver` protocol:

```python
class UrlResolver(Protocol):
    def can_resolve(self, netloc: str) -> bool:
        """Return True if this resolver handles URLs on the given domain."""
        ...

    def resolve(self, url: str) -> dict:
        """Resolve the URL and return a ParsedURLType-compatible dict.

        The 'url' key must be the platform-native video ID (used as
        youtube_id throughout the system).  Include a 'source_url' key
        with the original full URL so re-downloads work correctly.
        """
        ...
```

The parser calls resolvers in registration order.  The first resolver whose
`can_resolve()` returns `True` wins; if no resolver claims the URL a
`ValueError` is raised as before.

### Backend – Download Hooks

Download hooks implement the `DownloadHook` protocol:

```python
class DownloadHook(Protocol):
    def pre_download(self, obs, youtube_id, channel_id, config, channel_overwrites) -> dict:
        """Mutate obs in-place. Return a context dict passed to post_download."""
        ...

    def post_download(self, context, youtube_id, dl_cache, success) -> None:
        """Called after yt-dlp returns. context is the dict from pre_download."""
        ...
```

Hooks are called in registration order. `post_download` is called regardless of success so hooks
can clean up resources.

### Backend – Media Stream Enrichers

Media stream enrichers run when TubeArchivist extracts ffprobe stream metadata for a video:

```python
class MediaStreamEnricher(Protocol):
    def enrich_stream(self, stream, metadata) -> dict:
        """Return enriched metadata for one ffprobe stream."""
        ...
```

Use this when a fork feature needs extra UI-facing metadata for a media stream (for example,
audio language labels or cleaned track titles) without hardcoding that logic into the upstream
extractor.

### Frontend – Component Registry (`frontend/src/fork_features/registry.ts`)

Exports two arrays of React component constructors:

| Export | Rendered in | Props type |
|---|---|---|
| `APP_SETTINGS_SECTIONS` | `SettingsApplication.tsx` (Download Format box) | `AppSettingsSectionProps` |
| `CHANNEL_SETTINGS_SECTIONS` | `ChannelAbout.tsx` (Channel Customization box) | `ChannelSettingsSectionProps` |

Each upstream page renders fork sections with:

```tsx
import { APP_SETTINGS_SECTIONS } from '../fork_features/registry';
// ...
{APP_SETTINGS_SECTIONS.map((Section, i) => (
  <Section key={i} appSettingsConfig={appSettingsConfig} onRefresh={() => setRefresh(true)} />
))}
```

The frontend registry can also expose small fork-only formatter hooks for
upstream pages, such as stream-label formatters used by `Video.tsx`.

---

## Upstream Files Touched (Minimal Integration Points)

These are the upstream files intentionally touched by the fork framework. They should remain small,
well-commented integration points:

| File | What was added |
|---|---|
| `backend/config/settings.py` | `"fork_features"` in `INSTALLED_APPS` |
| `backend/appsettings/serializers.py` | Import `get_app_serializer_fields` + `get_fields()` override |
| `backend/appsettings/src/config.py` | Import `get_config_defaults` + `_effective_defaults()` method + `clear_old_keys()` uses it |
| `backend/channel/serializers.py` | Import `get_channel_serializer_fields` + `get_fields()` override |
| `backend/channel/src/index.py` | Import `get_channel_overwrite_keys` + extends `OVERWRITES` list |
| `backend/download/src/yt_dlp_handler.py` | Import `get_download_hooks` + pre/post hook calls + `download_target` override in `_dl_single_vid()` |
| `backend/video/src/media_streams.py` | Import `get_media_stream_enrichers` + enrichment hook call in audio stream extraction |
| `backend/video/serializers.py` | Optional stream metadata fields for enriched audio stream labels |
| `frontend/src/api/loader/loadAppsettingsConfig.ts` | Fork-only config fields added to the app settings TypeScript type |
| `frontend/src/pages/Channels.tsx` | Fork-only channel overwrite fields added to the shared channel type |
| `frontend/src/pages/Home.tsx` | Optional stream metadata fields added to the shared `StreamType` |
| `frontend/src/pages/SettingsApplication.tsx` | Import `APP_SETTINGS_SECTIONS` + `.map()` rendering block |
| `frontend/src/pages/ChannelAbout.tsx` | Import `CHANNEL_SETTINGS_SECTIONS` + `loadAppsettingsConfig` + `.map()` rendering block |
| `backend/video/views.py` | Import `serve_file_with_range` + three call-site replacements in `VideoStreamView` (mp4, cached transcode, fresh transcode) |
| `frontend/src/components/VideoPlayer.tsx` | Conditional `#t=` fragment – only appended when a saved position exists |
| `frontend/src/pages/Video.tsx` | Stream label formatter hook used to render enriched audio stream labels |

---

## Adding a New Feature

### 1 – Create a backend module

```
backend/fork_features/my_feature/
├── __init__.py      ← Must call register()
└── logic.py         ← Your feature logic
```

### 2 – Register in `__init__.py`

```python
"""my_feature – short description."""

from fork_features.registry import register
from rest_framework import serializers

# Define any serializer fields
_app_fields = {
    "my_setting": serializers.BooleanField(required=False, default=False),
}

# Define config defaults
_config_defaults = {
    "my_setting": False,
}

# Optionally implement a DownloadHook
from .logic import MyDownloadHook

register(
    feature_id="my_feature",
    config_defaults=_config_defaults,
    app_serializer_fields=_app_fields,
    # channel_serializer_fields={...},       # if needed
    # channel_overwrite_keys=["my_setting"], # if needed
    download_hook=MyDownloadHook(),           # if needed
    # media_stream_enricher=MyStreamEnricher(),
)
```

### 3 – Import in `backend/fork_features/apps.py`

Add your module to `ForkFeaturesConfig.ready()` so it self-registers at Django startup:

```python
class ForkFeaturesConfig(AppConfig):
    ...

    def ready(self) -> None:
        import fork_features.audio_tracks  # noqa: F401
        import fork_features.my_feature    # noqa: F401
```

### 4 – Create frontend components (if the feature has UI)

```
frontend/src/fork_features/myFeature/
├── MyFeatureControl.tsx          (optional feature-local helper component)
├── ApplicationSettingsSection.tsx   (if it needs global settings)
└── ChannelSettingsSection.tsx       (if it needs per-channel settings)
```

If a feature needs to customize display on an upstream page without owning a
full section, prefer a small formatter/helper exported from `src/fork_features`
and consumed through a registry hook rather than embedding fork logic directly
in the upstream page component.

Each component receives standardised props:

```ts
// For APPLICATION settings sections:
type AppSettingsSectionProps = {
  appSettingsConfig: AppSettingsConfigType;
  onRefresh: () => void;
};

// For CHANNEL settings sections:
type ChannelSettingsSectionProps = {
  channel: ChannelResponseType;
  appSettingsConfig: AppSettingsConfigType;
  onRefresh: () => void;
};
```

### 5 – Register frontend components

In `frontend/src/fork_features/registry.ts`:

```ts
import MyAppSection from './myFeature/ApplicationSettingsSection';
import MyChannelSection from './myFeature/ChannelSettingsSection';

export const APP_SETTINGS_SECTIONS: ComponentType<AppSettingsSectionProps>[] = [
  AudioTracksAppSection,   // existing
  MyAppSection,            // new
];

export const CHANNEL_SETTINGS_SECTIONS: ComponentType<ChannelSettingsSectionProps>[] = [
  AudioTracksChannelSection,  // existing
  MyChannelSection,           // new
];
```

That's it — the upstream pages pick up the new sections automatically.

---

## Staying In Sync With Upstream

> For the full branch policy, branch meanings, and the recurring upgrade workflow, see
> [BRANCHING.md](./BRANCHING.md).

### Branch strategy

`fork/main` is a permanent rolling integration branch that always contains every fork feature.
Stable release branches named `fork/<upstream-tag>` (e.g. `fork/v0.5.10`) are cut from
`fork/main` after each upstream release is merged and tested.

### Updating to a new upstream release

```bash
# 0. Make sure the working tree is clean and on fork/main
git fetch upstream --tags
git checkout fork/main
git pull --ff-only

# 1. Merge the new upstream tag into fork/main (one merge = one conflict round)
git merge --no-ff v0.6.0 -m "Merge upstream v0.6.0 into fork/main"

# 2. If conflicts appear, they will only be in the ~14 integration files listed
#    in "Upstream Files Touched" above. Resolution rule for every conflict:
#      keep upstream's change AND keep the fork hook line(s).
git diff --name-only --diff-filter=U   # list conflicted files
# edit each file, then:
git add <resolved-files>
git commit                             # completes the merge

# 3. Smoke-test (build backend + frontend, run a download, play a video)

# 4. Cut the new release branch from fork/main
git checkout -b fork/v0.6.0
git push -u origin fork/v0.6.0

# 5. Return to fork/main; it stays as the integration base for the next release
git checkout fork/main
git push origin fork/main
```

No cherry-picking, no per-commit conflict replays — the merge is resolved exactly once.

### Where conflicts can occur

Conflicts will only ever appear in the integration files listed in "Upstream Files Touched"
above. All code under `backend/fork_features/` and `frontend/src/fork_features/` is
self-contained and should have **no conflicts at all**.

For each conflict the resolution is always the same: keep upstream's change, then restore the
1–3 fork hook lines. Use `git checkout --theirs <file>` as a starting point when upstream
rewrote a whole function, then re-add the hook lines manually.

See [BRANCHING.md](./BRANCHING.md) for a conflict-resolution tip sheet and the full branch
lifecycle policy.

---

## Upstream Files Touched by `generic_downloads`

| File | What was added |
|---|---|
| `backend/fork_features/registry.py` | `UrlResolver` + `ChannelFallbackEnricher` protocols; corresponding fields on `_FeatureEntry`; `get_url_resolvers()` + `get_channel_fallback_enrichers()` accessors |
| `backend/common/src/urlparser.py` | `source_url: NotRequired[str]` on `ParsedURLType`; resolver hook call instead of ValueError for non-YouTube domains |
| `backend/common/src/index_generic.py` | `self.source_url` attribute on `YouTubeItem`; `build_yt_url()` returns it when set |
| `backend/download/src/queue.py` | Thread `source_url` through `_process_entry` → `_add_video` → `_parse_video`; persist in pending document |
| `backend/download/src/yt_dlp_handler.py` | Use `download_target` from hook context in `_dl_single_vid()`; pass `source_url` to `index_new_video()` |
| `backend/video/src/index.py` | `index_new_video()` accepts `source_url`; guards in `_validate_id`, `_get_ryd_stats`, `_get_sponsorblock` |
| `backend/channel/src/index.py` | 3-line `get_channel_fallback_enrichers()` hook call at end of `_video_fallback()` |
| `backend/channel/serializers.py` | Optional `channel_source_url` field on `ChannelSerializer` |

---

## Existing Fork Features

### Multi-Audio Language Download (`audio_tracks`)

Downloads additional audio language tracks alongside the primary stream and muxes them into the
final mp4 file.

**Backend** – `backend/fork_features/audio_tracks/`

| File | Description |
|---|---|
| `__init__.py` | Calls `register()` with config defaults, serializer fields, and download hook |
| `languages.py` | BCP-47 ↔ yt-dlp language code mapping |
| `media_streams.py` | Enriches extracted audio stream metadata for player labels |
| `ffmpeg_merge.py` | Merges extra audio tracks into the mp4 after download |
| `downloader.py` | `AudioTracksDownloadHook` – selects the primary audio language for the main yt-dlp format string (video + one audio); all extra DASH and HLS audio languages are downloaded as individual single-stream requests in post-download and merged via ffmpeg. This avoids yt-dlp's `check_formats: selected` silently dropping extra streams when a cookie+POT is configured. Each individual download uses a `bestaudio[language=X]/fallback_id` selector so yt-dlp picks the highest quality format for that language, respecting the user's global `format_sort` preference (codec/extension). Individual downloads attempt cookie-but-no-POT first, falling back to full config if needed. |

**Frontend** – `frontend/src/fork_features/audioTracks/`

| File | Description |
|---|---|
| `AudioLanguageSelector.tsx` | Feature-local language input used only by audio track settings |
| `ApplicationSettingsSection.tsx` | Toggle + language picker on the Application Settings page |
| `ChannelSettingsSection.tsx` | Per-channel override toggle + language picker on Channel About |
| `streamLabels.ts` | Feature-local formatter for audio stream labels on the Video page |

**Config keys** (added to `downloads` section):
- `audio_multistreams` (bool) – Enable/disable multi-audio track downloading
- `audio_languages` (string | null) – Comma-separated language codes to download

**Why upstream rejected it:** Chrome/Firefox do not natively support switching audio tracks in an
HTML5 `<video>` element without a custom player or server-side ffmpeg transcoding — both of which
are out of scope for the upstream project.

---

### Generic Downloads (`generic_downloads`)

Enables downloading individual video URLs from any website supported by
yt-dlp (e.g. Rumble, Vimeo, Dailymotion) by making the URL parsing and
download pipeline site-agnostic.

**Backend** – `backend/fork_features/generic_downloads/`

| File | Description |
|---|---|
| `__init__.py` | Calls `register()` with `url_resolver`, `download_hook`, and `channel_fallback_enricher` |
| `resolver.py` | `GenericUrlResolver` – accepts any non-YouTube URL; uses yt-dlp to probe the URL and return the canonical video ID + `source_url` |
| `downloader.py` | `GenericDownloadHook` – in `pre_download`, fetches `source_url` from the ES pending document and returns it as `download_target` so yt-dlp downloads from the correct platform URL |
| `channel_enricher.py` | `GenericChannelFallbackEnricher` – adds `channel_source_url` to fallback channel docs by reading `channel_url`/`uploader_url` from yt-dlp video metadata; enables Phase 2 subscription scanning |

**No frontend changes** – non-YouTube videos appear in the UI identically to
YouTube videos.  The user simply pastes a Rumble (or other) URL into the
download queue input.

**What works:** individual video downloads, metadata indexing, full-text
search, thumbnail, subtitles (if the platform provides them), watch history.

**What is skipped for non-YouTube videos:**
- SponsorBlock (YouTube-only API)
- Return YouTube Dislikes (YouTube-only API)
- Comments (YouTube-only extraction)

**Phase 2 (not yet implemented):** channel subscriptions for non-YouTube
sources — would require storing the channel's full URL and adapting
`remote_query.py`.

---

## Video Seek Fix (`streaming.py`)

**Root cause:** The fork's `VideoStreamView` (`backend/video/views.py`) serves video files using
Django's `FileResponse`, which does not handle HTTP `Range` requests.  When a browser seeks to
an arbitrary position in a `<video>` element it sends `Range: bytes=X-Y`.  Without a `206 Partial
Content` response the server sends the full file from byte 0, causing the player to restart from
the beginning.  A secondary issue: when no saved playback position exists the `<source>` URL ended
with `#t=` (empty value), which browsers interpret as `t=0`, further anchoring the start point.

**Fix summary:**

| File | Change |
|---|---|
| `backend/fork_features/streaming.py` *(new)* | `serve_file_with_range(request, path)` helper – parses the `Range` header, returns `206 Partial Content` with `Content-Range` when present, always sets `Accept-Ranges: bytes` |
| `backend/video/views.py` | Import + three one-line call replacements (direct mp4, cached transcode, fresh transcode) |
| `frontend/src/components/VideoPlayer.tsx` | `#t=${videoSrcProgress}` fragment only appended when `videoSrcProgress !== ''` |

**`serve_file_with_range` API:**

```python
from fork_features.streaming import serve_file_with_range

# Inside a Django view:
return serve_file_with_range(request, "/absolute/path/to/file.mp4")
# Optional content_type kwarg (default "video/mp4"):
return serve_file_with_range(request, path, content_type="video/mp4")
```

The helper is intentionally stateless and reusable – any future fork view that needs to stream
a binary file can import it directly without touching the upstream codebase.

---

## Disabling a Feature

To disable a feature without removing code:

1. **Backend**: Comment out or remove the feature import in `backend/fork_features/apps.py`
2. **Frontend**: Comment out or remove the component from the arrays in
   `frontend/src/fork_features/registry.ts`

The feature's code stays in the tree (no merge conflicts to deal with later) but is completely
inert.
