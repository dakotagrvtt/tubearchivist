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
2. fetch from `origin`
3. checkout `fork/v0.5.9` if needed
4. run `git pull --ff-only origin fork/v0.5.9`
5. run Docker Compose using the external compose file and the parent project
   directory so `build: ./tubearchivist` resolves correctly

Example:

```bash
bash scripts/deploy-server.sh
```

Override defaults with environment variables:

```bash
BRANCH=fork/v0.6.0 \
PROJECT_DIR=/zpool-8TB/containers/tubearchivist \
REPO_DIR=/zpool-8TB/containers/tubearchivist/tubearchivist \
COMPOSE_FILE=/zpool-8TB/containers/tubearchivist/docker-compose.yml \
bash scripts/deploy-server.sh
```

If you intentionally want to deploy with uncommitted local repo changes:

```bash
ALLOW_DIRTY=1 bash scripts/deploy-server.sh
```
