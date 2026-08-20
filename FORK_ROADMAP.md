# Fork roadmap

This document is the durable implementation plan for upcoming fork features.
It records product intent, ordering, architectural boundaries, and enough
current-state context for another agent to resume partially completed work.
It is a roadmap rather than a complete technical specification: verify the
current code before implementation and make the remaining design decisions in
the context of the version being changed.

Read `AGENTS.md`, `FORK_FEATURES.md`, and `BRANCHING.md` before starting work.
Substantial fork behavior belongs under `backend/fork_features/` or
`frontend/src/fork_features/`; changes to upstream-owned files should remain
small, documented integration hooks.

## Maintaining this roadmap

Use these status values:

- **Planned**: agreed work that has not started.
- **In progress**: implementation exists on a working branch but is incomplete.
- **Blocked**: progress requires a decision or external dependency.
- **Complete**: implemented, tested, documented, and delivered to the intended
  branch.
- **Deferred**: intentionally postponed and not part of the active sequence.

When working on a feature, update its handoff record with:

- the status and working branch;
- completed behavior and important decisions;
- remaining work or known limitations;
- relevant commits or pull requests;
- validation already performed and validation still required.

Do not mark a feature complete merely because its main UI exists. Verify its
backend lifecycle, cleanup and failure paths, frontend behavior, documentation,
and production-like deployment path. Preserve the priority order unless the
project owner explicitly changes it.

## Current playback-cache baseline

The fork currently creates two kinds of derived playback data beneath the
configured cache directory:

- `transcode/<video-id>.mp4` contains persistent browser-compatible MP4 files
  prepared from incompatible source containers. These are invalidated when the
  archived source is replaced, but do not currently have general age or size
  cleanup.
- `hls/<video-id>/` contains the video, alternate-audio playlists, and segments
  used for multi-audio playback. HLS cleanup currently uses a fixed seven-day
  maximum age and 10 GiB global limit. Oldest modification time is used for
  eviction, which is not a true record of most recent playback.

Both caches contain reproducible derivatives, never the authoritative archive.
Cache-management actions must not delete archived media or its indexed
metadata.

## Active priorities

Implement these features in order. Later items may build on interfaces created
by earlier work, but each should remain a focused, independently reviewable
change.

### 1. Playback-cache management

**Status:** Planned

#### Intended outcome

Users can understand and control the disk space consumed by prepared playback
media. Application settings expose retention policy, while appropriate
application and video views expose cache state and safe actions.

The feature should cover both prepared MP4 and multi-audio HLS caches:

- total usage and usage by cache type;
- configurable retention and storage limits;
- actual least-recently-used cleanup based on playback access rather than file
  creation or modification time alone;
- per-video cache status, size, and last-use information when available;
- per-video **Prepare**, **Retry**, and **Remove** operations appropriate to the
  video's current state;
- a global cleanup action with a clear preview or result summary.

Removing cache data must be safe during concurrent playback or preparation.
Cleanup must avoid partial artifacts and active jobs, recover consistently from
interruption, and clear related transient status without touching source media.
Configuration changes should take effect without requiring operators to edit
container files manually.

#### General implementation direction

Extend the playback feature's existing cache lifecycle instead of creating an
unrelated cleanup subsystem. The backend will need a single inventory and
policy layer shared by startup cleanup, post-generation cleanup, API reporting,
and explicit user actions. Persist only the access metadata needed for reliable
LRU behavior and tolerate missing or stale records.

Expose narrow authenticated API operations and register configuration through
the fork settings boundary. Add frontend management UI under the fork playback
feature. Keep potentially expensive directory scans away from ordinary page
rendering, and make long-running preparation asynchronous through the existing
task infrastructure.

Implementation should decide, document, and test:

- whether MP4 and HLS use separate quotas or share a global quota;
- the minimum useful retention values and safe defaults for upgrades;
- when a playback counts as an access and how often that timestamp is written;
- how removal behaves when a file is being streamed or generated;
- how unavailable, queued, preparing, ready, failed, and stale states map to
  the available per-video controls.

#### Completion criteria

- Usage totals agree with the files on disk and distinguish cache types.
- Retention and size settings survive restart and have documented defaults.
- Recently used entries survive quota cleanup ahead of less recently used
  entries.
- Per-video operations are idempotent and cannot remove archived originals.
- Active-job, partial-failure, replacement, and restart behavior has regression
  coverage.
- The frontend build, relevant backend tests, full backend suite, and a
  production-like cache smoke test pass.

#### Handoff record

- Branch: not started
- Completed: none
- Remaining: all work described above
- Decisions: none recorded
- Commits or pull requests: none
- Validation: none

### 2. Playback source indicator

**Status:** Planned

#### Intended outcome

The enhanced player unobtrusively identifies the source it is actually using,
so users and support logs can distinguish delivery paths without interpreting
URLs or generic fallback messages. The indicator should distinguish at least:

- direct playback of the archived source;
- a prepared browser-compatible MP4;
- cached multi-audio HLS;
- fallback from HLS or prepared playback to a direct source.

It should describe the effective source, not merely the source initially
requested. If playback changes source after an error or retry, the indicator
must update. A compact label may expose additional diagnostic detail through a
tooltip or expandable status, but normal users should not see internal paths or
implementation jargon without explanation.

#### General implementation direction

Make source kind explicit in the preparation hooks and player state rather than
inferring it from a URL in the rendered component. Backend responses may need a
small, stable source/status field where the frontend cannot determine the
answer reliably. Reuse the same state in later progress and error reporting so
the player does not maintain competing interpretations of its active source.

Account for direct MP4 range serving, persistent transcodes, multi-audio HLS,
disabled fork features, retries, and runtime HLS failure. The native-player
fallback should remain functional even if it cannot display the enhanced
indicator.

#### Completion criteria

- Every supported source path has a clear, accurate label.
- Runtime fallback and retry update the label without reloading the page.
- The indicator remains readable on narrow mobile layouts.
- No protected filesystem path, token, or sensitive diagnostic detail is
  exposed.
- Source-selection and fallback transitions have focused frontend tests.

#### Handoff record

- Branch: not started
- Completed: none
- Remaining: all work described above
- Decisions: none recorded
- Commits or pull requests: none
- Validation: none

### 3. Real transcode progress and clearer preparation errors

**Status:** Planned

#### Intended outcome

Replace indefinite preparation messages and generic failures with trustworthy,
actionable status for prepared MP4 and multi-audio HLS generation. Users should
see meaningful stages such as queued, transcoding, finalizing, and ready, plus
percentage or processed-time progress when it can be calculated reliably.

Failures should identify a useful category and next action. Examples include a
missing or replaced source, unsupported or corrupt streams, an unavailable
worker, loss of the preparation lock, insufficient storage, a cache-policy
rejection, or invalid generated output. User-facing messages should remain
brief, while bounded technical details are available to operators without
leaking private paths or unbounded FFmpeg output.

#### General implementation direction

Capture structured FFmpeg progress and a bounded diagnostic tail instead of
discarding all process output. Combine processed media time with probed source
duration where possible, throttle shared-state writes, and retain the existing
ownership-token protections. Progress must be monotonic enough to be useful but
must not claim precision the underlying media cannot provide.

Define stable backend status and error categories consumed by both preparation
hooks. The frontend should poll or subscribe using the existing task boundary,
show progress without disrupting playback fallback, and present an appropriate
retry action. Integrate with the cache-management states from priority 1 and
the effective-source state from priority 2 rather than duplicating them.

#### Completion criteria

- Compatible MP4 and HLS jobs expose stage and measurable progress.
- Progress updates are bounded and do not overload Redis or the API.
- Known failure paths produce stable categories and actionable messages.
- Captured diagnostics have size limits and redact sensitive local details.
- Retry, restart, stale-source, worker-loss, and failed-output paths have
  regression coverage.
- Mobile and desktop UI clearly distinguish preparation from playback failure.

#### Handoff record

- Branch: not started
- Completed: none
- Remaining: all work described above
- Decisions: none recorded
- Commits or pull requests: none
- Validation: none

### 4. SponsorBlock segments on the timeline

**Status:** Planned

#### Intended outcome

Display available SponsorBlock segments as recognizable regions on the video
timeline. The initial feature is informational: it should help users see and
identify segments without silently changing playback behavior.

Segment categories need distinct but accessible styling, readable labels, and
sensible handling of overlapping or malformed ranges. Absence of SponsorBlock
data or failure of the external service must never prevent ordinary playback.
Any future automatic or manual skipping behavior requires a separate product
decision and should not be implied by the timeline implementation.

#### General implementation direction

Keep external-service access and normalization behind a fork-owned backend
boundary so credentials, request policy, caching, rate limits, and failures are
handled consistently. Decide whether data is collected during indexing or
loaded on demand, balancing playback latency, privacy, API limits, and stale
data. Store or cache only the normalized fields required by the player.

Expose segments to the frontend in a stable media-time representation and
render them through the enhanced player's timeline facilities. Avoid coupling
the feature to one SponsorBlock response shape throughout the UI. Provide an
application-level switch and category controls if the final design makes
external requests or visual density user-configurable.

#### Completion criteria

- Valid segments align correctly with duration and seeking behavior.
- Categories remain distinguishable with keyboard navigation, high contrast,
  mobile controls, and common forms of color-vision deficiency.
- Overlapping, out-of-range, missing, stale, and failed responses degrade
  safely.
- External requests are cached, bounded, observable, and documented.
- Disabling the feature stops its external activity and removes its timeline
  UI without affecting playback.

#### Handoff record

- Branch: not started
- Completed: none
- Remaining: all work described above
- Decisions: none recorded
- Commits or pull requests: none
- Validation: none

## Larger changes for later

These ideas are intentionally deferred until the active playback priorities are
complete. They will require separate discovery and a more detailed plan before
implementation.

### Rules-based archive filters

**Status:** Deferred

Allow users to define reusable rules that classify, include, exclude, or find
archived content based on metadata such as channel, age, duration, watched
state, tags, or other indexed fields. The design must make rule precedence and
previewing understandable, prevent accidental destructive bulk operations, and
fit Elasticsearch query and migration boundaries.

### Per-user playback history, preferences, and libraries

**Status:** Deferred

Move suitable browser-global and application-global playback state into
authenticated user scope. Expected areas include progress/history, subtitle and
audio preferences, playback behavior, saved collections, and personal library
views. This requires an explicit identity, authorization, storage, migration,
and privacy model before UI work begins.

### Synchronized transcript

**Status:** Deferred; previously declined

A future transcript could provide time-synchronized highlighting,
click-to-seek, and text search. It would need a defined transcript source,
language and subtitle relationship, indexing strategy, accessibility behavior,
and storage policy. Do not begin implementation without renewed approval from
the project owner.

## Explicitly not planned

Seek or chapter thumbnail generation is not on this roadmap. The current
chapter feature uses an in-memory WebVTT track and creates no thumbnail sprites.
Generated seek thumbnails would add derivative image files across the archive;
their storage and maintenance cost is not currently justified. If reconsidered,
they should be treated as a small, on-demand, LRU-managed cache rather than
permanent archive data and should receive a separate product decision.
