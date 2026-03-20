# Fork Features – Maintainer Guide

This document explains how custom features that diverge from upstream
[TubeArchivist](https://github.com/tubearchivist/tubearchivist) are structured so that:

1. **Upstream merges stay clean** — fork-only code lives in isolated directories and is hooked
   into upstream files with the smallest possible diff.
2. **New features are easy to add** — drop a new module, call `register()` in the registry; no
   surgery on upstream page components required.
3. **Features can be toggled off** — removing or commenting out a single `register()` call in a
   feature's `__init__.py` disables it everywhere.

---

## Directory Layout

```
backend/
└── fork_features/               ← Python package, isolated from upstream apps
    ├── __init__.py              ← Triggers feature auto-registration
    ├── apps.py                  ← Django AppConfig (listed in INSTALLED_APPS)
    ├── registry.py              ← Central registry: register() + accessor functions
    └── audio_tracks/            ← "Multi-audio language download" feature
        ├── __init__.py          ← Calls registry.register() with feature hooks
        ├── languages.py         ← ISO language helpers
        ├── ffmpeg_merge.py      ← Post-download ffmpeg muxing logic
        └── downloader.py        ← DownloadHook implementation (pre/post download)

frontend/
└── src/fork_features/           ← TypeScript/React, isolated from upstream components
    ├── registry.ts              ← Exports APP_SETTINGS_SECTIONS, CHANNEL_SETTINGS_SECTIONS
    └── audioTracks/
        ├── ApplicationSettingsSection.tsx
        └── ChannelSettingsSection.tsx
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

Each upstream file contains a single import and a small integration call — nothing else changes.

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

---

## Upstream Files Touched (Minimal Integration Points)

These are the **only** upstream files modified by the fork framework. Each has 1-3 lines added:

| File | What was added |
|---|---|
| `backend/config/settings.py` | `"fork_features"` in `INSTALLED_APPS` |
| `backend/appsettings/serializers.py` | Import `get_app_serializer_fields` + `get_fields()` override |
| `backend/appsettings/src/config.py` | Import `get_config_defaults` + `_effective_defaults()` method + `clear_old_keys()` uses it |
| `backend/channel/serializers.py` | Import `get_channel_serializer_fields` + `get_fields()` override |
| `backend/channel/src/index.py` | Import `get_channel_overwrite_keys` + extends `OVERWRITES` list |
| `backend/download/src/yt_dlp_handler.py` | Import `get_download_hooks` + pre/post hook calls in `_dl_single_vid()` |
| `frontend/src/pages/SettingsApplication.tsx` | Import `APP_SETTINGS_SECTIONS` + `.map()` rendering block |
| `frontend/src/pages/ChannelAbout.tsx` | Import `CHANNEL_SETTINGS_SECTIONS` + `loadAppsettingsConfig` + `.map()` rendering block |

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
)
```

### 3 – Import in `backend/fork_features/__init__.py`

Add your module to the imports list:

```python
from fork_features import audio_tracks   # existing
from fork_features import my_feature     # new
```

### 4 – Create frontend components (if the feature has UI)

```
frontend/src/fork_features/myFeature/
├── ApplicationSettingsSection.tsx   (if it needs global settings)
└── ChannelSettingsSection.tsx       (if it needs per-channel settings)
```

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

Conflicts will almost always be limited to the small hook lines in the 8 upstream files listed
above. The bulk of your feature code in `fork_features/` will have **no conflicts at all**.

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
| `ffmpeg_merge.py` | Merges extra audio tracks into the mp4 after download |
| `downloader.py` | `AudioTracksDownloadHook` – injects multi-audio yt-dlp options pre-download, runs ffmpeg merge post-download |

**Frontend** – `frontend/src/fork_features/audioTracks/`

| File | Description |
|---|---|
| `ApplicationSettingsSection.tsx` | Toggle + language picker on the Application Settings page |
| `ChannelSettingsSection.tsx` | Per-channel override toggle + language picker on Channel About |

**Config keys** (added to `downloads` section):
- `audio_multistreams` (bool) – Enable/disable multi-audio track downloading
- `audio_languages` (string | null) – Comma-separated language codes to download

**Why upstream rejected it:** Chrome/Firefox do not natively support switching audio tracks in an
HTML5 `<video>` element without a custom player or server-side ffmpeg transcoding — both of which
are out of scope for the upstream project.

---

## Disabling a Feature

To disable a feature without removing code:

1. **Backend**: Comment out or remove the import in `backend/fork_features/__init__.py`
2. **Frontend**: Comment out or remove the component from the arrays in
   `frontend/src/fork_features/registry.ts`

The feature's code stays in the tree (no merge conflicts to deal with later) but is completely
inert.
