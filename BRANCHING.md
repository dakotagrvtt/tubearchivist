# Branching strategy

The fork is maintained from `origin/fork/main`, which is based on the
upstream project and contains the fork integration. Stable deployments use a
versioned `fork/vX.Y.Z` branch cut after testing.

## Branch roles

- `fork/main`: rolling integration branch; merge upstream releases and land
  feature work here. It may be temporarily unstable.
- `fork/vX.Y.Z`: frozen deployment and rollback branch. Create it from a
  tested `fork/main`; fixes are made on a short-lived branch and then merged
  back to both the release branch and `fork/main` when appropriate.
- `feat/*`, `fix/*`, `docs/*`, `rewrite/*`: short-lived focused work branches.
- `develop` and `resync/upstream-develop`: legacy upstream-sync branches. They
  were useful while comparing upstream histories, but they are not the fork's
  integration or deployment target. The old `develop` snapshot also contains
  broken fork merge remnants; preserve it for reference until no longer
  needed, then delete it explicitly.

## Upstream release workflow

```bash
git fetch upstream --tags
git switch fork/main
git pull --ff-only
git merge --no-ff vX.Y.Z -m "Merge upstream vX.Y.Z into fork/main"
# resolve, test, and commit
git switch -c fork/vX.Y.Z
git push -u origin fork/vX.Y.Z
git switch fork/main
```

Resolve conflicts at the small, documented integration points. Code under
`backend/fork_features/` and `frontend/src/fork_features/` should not need
upstream conflict resolution. Run backend compile/tests, the frontend build,
and a deployed playback/download smoke test before cutting a release branch.

## Deployment

Deploy a stable branch, not a moving work branch:

```bash
git clone --branch fork/vX.Y.Z <fork-url>
docker compose up --build -d
```

Verify the branch and commit on the deployment host, then verify the watcher
or runtime picked up that commit. A successful local build is not proof that a
remote deployment is running it.
