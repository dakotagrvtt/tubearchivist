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

- `fork/main`
  - **permanent rolling integration branch** — always contains every fork feature
  - upstream releases are merged here first; new release branches are cut from here
  - use this branch for day-to-day fork development

- `fork/v0.5.10`
  - frozen stable release branch — rollback point for the v0.5.10 deployment
  - do not commit to it directly; use `fork/main` and cut a new release branch

- `develop` / `resync/upstream-develop`
  - legacy branches left over from earlier sync work
  - superseded by `fork/main`; safe to delete when no longer needed

- `origin/master`
  - exists remotely; not the preferred deployment branch for fork-specific work

- `upstream/develop` and `upstream/master`
  - original project tracking refs used as the source for upstream tag merges

---

## Branch Roles

### 1) Rolling integration branch — `fork/main`

- permanent; always contains every fork feature
- upstream releases are merged here first; conflict resolution happens here
- new features and fixes are developed here before release branching
- may be temporarily unstable; do not deploy directly from it

### 2) Stable fork release branches — `fork/vX.Y.Z`

Format: `fork/v0.5.10`, `fork/v0.6.0`, etc.

- cut from `fork/main` after each upstream release is merged and tested
- frozen once created; do not commit to them after deployment
- best branch for production deploys and rollback points
- safe to clone from on another machine

### 3) Short-lived work branches

Format: `fix/<topic>`, `feat/<topic>`, `docs/<topic>`

- focused work for a single change
- merged or cherry-picked back into `fork/main`

### 4) Resync / migration branches — `resync/*`

- temporary; used to replay or compare changes during large refactors
- assume temporary unless explicitly promoted to another role

---

## Recommended Workflow

### Upstream sync workflow

The goal is to do conflict resolution exactly once per upstream release.
`fork/main` always contains every fork feature, so merging a new upstream tag
into it is sufficient — there is no need to replay fork commits or
cherry-pick.

```bash
# 0. Clean working tree, on fork/main
git fetch upstream --tags
git checkout fork/main
git pull --ff-only

# 1. Merge the new upstream stable TAG (not a branch) into fork/main
git merge --no-ff v0.6.0 -m "Merge upstream v0.6.0 into fork/main"

# 2. Resolve conflicts — they will only appear in the ~14 integration files
#    listed in FORK_FEATURES.md "Upstream Files Touched".
#    Rule: keep upstream's change AND keep the fork hook line(s).
git diff --name-only --diff-filter=U   # see only conflicted files
# edit, then:
git add <resolved-files>
git commit                             # completes the merge

# 3. Smoke-test (build, run a download, play a video)

# 4. Cut the new stable release branch
git checkout -b fork/v0.6.0
git push -u origin fork/v0.6.0

# 5. Return to fork/main for ongoing development
git checkout fork/main
git push origin fork/main
```

**Why merging a tag beats cherry-picking:** cherry-picking N commits means
resolving the same hook-line conflicts up to N times. A single `git merge
<tag>` resolves everything once.

**Conflict-resolution tips:**
- `git diff --name-only --diff-filter=U` lists only conflicted files.
- `git checkout --theirs <file>` is fast when upstream rewrote a whole
  function — grab their version, then re-add the 1–3 fork hook lines.
- Files under `backend/fork_features/` and `frontend/src/fork_features/` are
  fork-only and should never conflict; if they do, fork code has leaked
  outside the isolation directories.

### Hotfix workflow

If the deployed `fork/vX.Y.Z` branch needs a small fix:

```bash
git checkout fork/v0.5.10
git checkout -b fix/my-fix
# make and test the fix
git checkout fork/v0.5.10
git merge --ff-only fix/my-fix
git push origin fork/v0.5.10
```

Then port the fix back to `fork/main` if it is still applicable:

```bash
git checkout fork/main
git cherry-pick <fix-commit>
git push origin fork/main
```

---

## Deployment Guidance

For deployment on another machine, prefer a stable fork branch such as:

- `fork/v0.5.10`

Example:

```bash
git clone --branch fork/v0.5.10 https://github.com/dakotagrvtt/tubearchivist.git && cd tubearchivist && docker compose up --build -d
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
git push --force-with-lease origin fork/v0.5.10
```

---

## Practical Rules for Future Maintenance

- Do **not** use one always-moving branch as the only deployment target.
- Keep at least one **stable versioned fork branch** for production use.
- Keep fork-only behavior modular under `backend/fork_features/` and
  `frontend/src/fork_features/`.
- Do upstream integration work on `fork/main` first.
- Promote tested changes to a stable `fork/vX.Y.Z` branch afterward.

---

## Cleanup Status

- [x] `fork/main` established as the rolling integration branch
- [x] `fork/vX.Y.Z` as stable deployment branches
- [ ] Delete legacy `develop` and `resync/upstream-develop` once confirmed no
      longer needed