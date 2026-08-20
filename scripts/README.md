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

1. verify the repo and compose paths exist
2. take an exclusive deployment lock for the project directory
3. fetch `fork/v0.5.11` from `origin` and require a clean checkout that can be
   fast-forwarded to the exact remote commit
4. validate the external Compose file
5. build the application image with `--pull` and the Docker build cache
6. recreate containers, remove orphaned Compose containers, and wait up to 300
   seconds for running or healthy services
7. verify that `/api/health/` reaches the Django API inside the Tube Archivist
   container
8. run Docker Compose using the external compose file and the parent project
   directory so `build: ./tubearchivist` resolves correctly

The script does not prune Docker state. Named volumes and image caches remain
available for rollback and for the next build.

The deployment host must provide Git, `flock`, Docker, and Docker Compose v2
with support for `docker compose up --wait`. A local branch that is ahead of or
diverged from its remote is rejected so the reported commit always identifies
the fetched release. The explicit API probe protects against an external
Compose healthcheck that only verifies Nginx. A failed readiness check prints
`docker compose ps` and exits nonzero; it does not automatically roll
containers back.

Example:

```bash
./scripts/deploy-server.sh
```

Override defaults with environment variables:

```bash
BRANCH=fork/v0.5.11 \
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
