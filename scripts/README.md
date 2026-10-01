# Server Deployment Scripts

## `deploy-server.sh`

Deploys the fork on a server where the git checkout and the active
`docker-compose.yml` are stored in different locations.

Default expected layout:

```text
/zpool-8TB/containers/tubearchivist/
├── docker-compose.yml
└── tubearchivist/
```

Default behavior:

1. resolve repo and Compose paths relative to the invocation directory
2. take an exclusive deployment lock without dirtying the checkout
3. explicitly fetch `fork/v0.5.12` from `origin`, including in single-branch
   clones, and require a clean checkout that can fast-forward to that commit
4. validate that the `tubearchivist` service builds from this checkout using
   the repository Dockerfile's final stage
5. build the application with `--pull` and the Docker build cache, using a
   project-specific image tag containing the full commit and a revision label
6. start services, recreating those whose image or configuration changed,
   remove orphaned Compose containers, and wait for running or healthy services
7. verify that the running application's image ID matches the built image
8. verify the Django API and ping this container's Celery worker through Redis
   within the remaining readiness deadline

The application requires a `build` definition. Image-only configurations,
different build contexts, custom Dockerfiles, intermediate build targets, and
mounts that replace `/app` code are rejected. Media and cache mounts remain
supported. Use `build: ./tubearchivist` for the default layout, or `build: .`
when the project directory is the checkout.

`deploy_config.py` reads resolved Compose JSON and creates a temporary override
for the image tag, revision label, and `pull_policy: never`. The server's Compose
file is not changed, and the override is removed on exit. Startup uses
`--no-build` so it cannot substitute a second build for the verified image.
Use this script for deployments; a manual `docker compose up` without the
override uses the original Compose image setting instead. The success message
records the full commit and running image ID.

Unchanged Elasticsearch and Redis services are not forcibly restarted. They
can still be recreated when their configuration or local image changes.
The lock remains in the project directory for the external layout. If that
directory is inside the checkout, the lock is stored in Git metadata instead.

The script does not prune Docker state. Named volumes and image caches remain
available for rollback and for the next build.

The deployment host must provide Git, `flock`, Python 3, GNU `realpath` and
`timeout`, Docker, and Docker Compose with JSON config output and support for
`docker compose up --wait`. Keep `deploy_config.py` beside `deploy-server.sh`.
A local branch that is ahead of or diverged from its remote is rejected.
The explicit API probe protects against a healthcheck that only verifies
Nginx. The worker check targets `celery@<container-hostname>`, matching the
repository's worker startup command, so another worker sharing Redis cannot
satisfy it. Each probe is bounded by the remaining readiness budget.
A failed readiness or running-image check prints `docker compose ps` and exits
nonzero; it does not automatically roll containers back.

Example:

```bash
./scripts/deploy-server.sh
```

Override defaults with environment variables:

```bash
BRANCH=fork/v0.5.12 \
PROJECT_DIR=/zpool-8TB/containers/tubearchivist \
REPO_DIR=/zpool-8TB/containers/tubearchivist/tubearchivist \
COMPOSE_FILE=/zpool-8TB/containers/tubearchivist/docker-compose.yml \
./scripts/deploy-server.sh
```

Set `NO_CACHE=1` when troubleshooting requires a completely clean image build:

```bash
NO_CACHE=1 ./scripts/deploy-server.sh
```

Override the complete readiness deadline with a positive number of seconds:

```bash
WAIT_TIMEOUT=600 ./scripts/deploy-server.sh
```
