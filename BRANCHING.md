# Branching Strategy – Fork Maintenance Guide

This document records the current branch structure for this TubeArchivist fork
and the intended workflow for keeping the fork maintainable over time.

The goal is to make future maintenance predictable for both humans and AI
assistants:

1. keep upstream sync work separate from fork feature work,
2. keep a stable branch that can be deployed at any time,
3. avoid losing track of which branch is experimental vs. release-ready.

---

## Remotes

- `upstream` → the original TubeArchivist project
  - `https://github.com/tubearchivist/tubearchivist.git`
- `origin` → this fork
  - `https://github.com/dakotagrvtt/tubearchivist.git`

---

## Current Branches

As of the current documented state:

- `fork/v0.5.9`
  - current fork release branch
  - contains the modular fork-features framework
  - contains the audio-tracks feature and player-label metadata restoration
  - intended to be the stable deployment branch right now

- `resync/upstream-develop`
  - historical/upstream-resync working branch
  - used while integrating or replaying fork changes onto newer upstream code
  - not intended as the main deployment target

- `develop`
  - fork-side development branch currently present on `origin`
  - should be treated as a general development/integration branch, not the
    only source of truth for deployment

- `origin/master`
  - exists remotely, but should not be assumed to be the preferred deployment
    branch for fork-specific work

- `upstream/develop` and `upstream/master`
  - original project tracking refs
  - used as the source of incoming upstream updates

---

## Branch Roles

The recommended meaning of branch names in this fork is:

### 1) Stable fork release branches

Format:

- `fork/v0.5.9`
- `fork/v0.6.0`
- etc.

Purpose:

- stable, deployable branch
- tied to a specific upstream version/tag or release baseline
- safe place to clone from on another machine
- best branch for production deployments and rollback points

Rules:

- do not use these as scratch branches
- only merge/cherry-pick tested fork changes onto them
- prefer deploying from these branches or from tags created on top of them

### 2) Rolling integration branch

Recommended future name:

- `fork/main`

or, if you want to stay closer to TubeArchivist naming:

- `fork/develop`

Purpose:

- ongoing integration branch for fork work
- where upstream changes are merged/rebased in first
- where new fork features are developed before release branching

Rules:

- can move frequently
- may be temporarily unstable
- should not be the only deployment branch

### 3) Resync / migration branches

Format:

- `resync/upstream-develop`
- `resync/<purpose>`

Purpose:

- temporary branches used to replay, compare, or resync fork changes against
  upstream
- useful during large refactors or when reconstructing a clean fork overlay

Rules:

- assume temporary unless explicitly promoted
- do not treat as permanent deployment targets

### 4) Short-lived work branches

Format:

- `fix/<topic>`
- `feat/<topic>`
- `docs/<topic>`

Purpose:

- focused work branches for a specific change
- merged or cherry-picked into the rolling integration branch

---

## Recommended Workflow

### Upstream sync workflow

1. fetch latest upstream changes
2. update the rolling fork integration branch first
3. test the fork features there
4. cut or update a stable `fork/vX.Y.Z` branch once validated

Example (using `develop` as the current rolling integration branch; update to
`fork/main` once that branch is created per the cleanup plan):

```bash
git fetch upstream --tags
git checkout develop
git merge upstream/develop
# or: git rebase upstream/develop
```

Then, after validation:

```bash
git checkout -b fork/v0.6.0
git push origin fork/v0.6.0
```

### Hotfix workflow

If a deployed fork release needs a small fix:

```bash
git checkout fork/v0.5.9
git checkout -b fix/player-labels
# make and test the fix
git checkout fork/v0.5.9
git merge --ff-only fix/player-labels
git push origin fork/v0.5.9
```

Then port the same fix back to the rolling integration branch if needed.

---

## Deployment Guidance

For deployment on another machine, prefer a stable fork branch such as:

- `fork/v0.5.9`

Example:

```bash
git clone --branch fork/v0.5.9 https://github.com/dakotagrvtt/tubearchivist.git && cd tubearchivist && docker compose up --build -d
```

For an existing server install that keeps a custom `docker-compose.yml` outside
the repo checkout, see `scripts/deploy-server.sh` and `scripts/README.md`.

Before using that on another machine, make sure:

- the branch is pushed to GitHub,
- the desired commits are present on that branch,
- `docker-compose.yml` has the intended deployment settings,
- especially values like `TA_HOST`, credentials, timezone, and
  `TA_AUTO_UPDATE_YTDLP`.

---

## Git Identity / Push Notes

If GitHub email privacy is enabled, use the GitHub noreply address locally:

```bash
git config user.name "Dakota Gravitt"
git config user.email "19499852+dakotagrvtt@users.noreply.github.com"
```

If existing local commits used the wrong email, rewrite them before pushing.

Single latest commit:

```bash
git commit --amend --no-edit --reset-author
```

Multiple local commits:

```bash
git rebase -i --root --exec 'git commit --amend --no-edit --reset-author'
```

Then push with:

```bash
git push --force-with-lease origin fork/v0.5.9
```

---

## Practical Rules for Future Maintenance

- Do **not** use one always-moving branch as the only deployment target.
- Keep at least one **stable versioned fork branch** for production use.
- Keep fork-only behavior modular under `backend/fork_features/` and
  `frontend/src/fork_features/`.
- Do upstream integration work on a rolling branch first.
- Promote tested changes to a stable `fork/vX.Y.Z` branch afterward.
- If needed, create release tags on top of stable fork branches for especially
  important deployment points.

---

## Suggested Next Cleanup

To simplify the repo over time, consider standardizing on:

- `fork/main` → rolling integration branch
- `fork/vX.Y.Z` → stable deployment branches
- `resync/*` → temporary migration/resync branches only

This is not required immediately, but it is the clearest long-term layout.