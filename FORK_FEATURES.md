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
| `get_media_stream_enrichers()` | `video/src/media_streams.py` → `_extract_audio_metadata()` | Enriches extracted stream metadata for fork-specific UI |

Each upstream file contains a small, explicit integration point. The goal is to keep upstream
diffs narrow and predictable, even if a given file needs slightly more than 1-3 added lines.

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
| `backend/download/src/yt_dlp_handler.py` | Import `get_download_hooks` + pre/post hook calls in `_dl_single_vid()` |
| `backend/video/src/media_streams.py` | Import `get_media_stream_enrichers` + enrichment hook call in audio stream extraction |
| `backend/video/serializers.py` | Optional stream metadata fields for enriched audio stream labels |
| `frontend/src/api/loader/loadAppsettingsConfig.ts` | Fork-only config fields added to the app settings TypeScript type |
| `frontend/src/pages/Channels.tsx` | Fork-only channel overwrite fields added to the shared channel type |
| `frontend/src/pages/Home.tsx` | Optional stream metadata fields added to the shared `StreamType` |
| `frontend/src/pages/SettingsApplication.tsx` | Import `APP_SETTINGS_SECTIONS` + `.map()` rendering block |
| `frontend/src/pages/ChannelAbout.tsx` | Import `CHANNEL_SETTINGS_SECTIONS` + `loadAppsettingsConfig` + `.map()` rendering block |
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

> For the full branch policy and current branch meanings, see
> [BRANCHING.md](./BRANCHING.md).

### Branch strategy

Fork features live on branches named `fork/<upstream-tag>`, e.g. `fork/v0.5.9`. Each branch is
based on a stable upstream tag with the fork-features commit(s) applied on top.

### Updating to a new upstream release

```bash
# 1. Fetch new upstream tags
git fetch upstream --tags

# 2. Create a new fork branch from the new tag
git checkout -b fork/v0.6.0 v0.6.0

# 3. Cherry-pick the fork-features commit(s) from the old branch
git cherry-pick fork/v0.5.9          # or a specific commit hash

# 4. Resolve any conflicts (usually just the hook lines in upstream files)
#    For each conflict: keep the upstream change AND restore the hook line.
git add <resolved-files>
git cherry-pick --continue

# 5. Test, then push
git push origin fork/v0.6.0
```

### Where conflicts can occur

Conflicts will almost always be limited to the small hook lines in the integration files listed
above. The bulk of your feature code in `backend/fork_features/` and
`frontend/src/fork_features/` should have **no conflicts at all**.

For each conflict, the resolution is always the same pattern: keep whatever upstream changed,
then re-add the 1-3 fork hook lines.

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
| `downloader.py` | `AudioTracksDownloadHook` – selects the primary audio language for the main yt-dlp format string (video + one audio); all extra DASH and HLS audio languages are downloaded as individual single-stream requests in post-download and merged via ffmpeg. This avoids yt-dlp's `check_formats: selected` silently dropping extra streams when a cookie+POT is configured. Individual extra-track downloads attempt cookie-but-no-POT first to avoid POT interference with DASH audio URLs, falling back to the full config if needed. |

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

## Disabling a Feature

To disable a feature without removing code:

1. **Backend**: Comment out or remove the feature import in `backend/fork_features/apps.py`
2. **Frontend**: Comment out or remove the component from the arrays in
   `frontend/src/fork_features/registry.ts`

The feature's code stays in the tree (no merge conflicts to deal with later) but is completely
inert.
