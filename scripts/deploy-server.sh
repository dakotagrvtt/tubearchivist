#!/usr/bin/env bash

set -euo pipefail

# Deploy this fork on a server where:
# - the git checkout lives in a repo directory, and
# - the active docker-compose.yml lives in a parent/external directory.
#
# Default layout expected by this script:
#   /zpool-8TB/containers/tubearchivist/
#   ├── docker-compose.yml        <- custom compose file in use on server
#   └── tubearchivist/            <- git checkout of this repository
#
# Override any of these with environment variables if needed:
#   PROJECT_DIR, REPO_DIR, COMPOSE_FILE, BRANCH, REMOTE, ALLOW_DIRTY

PROJECT_DIR="${PROJECT_DIR:-/zpool-8TB/containers/tubearchivist}"
REPO_DIR="${REPO_DIR:-${PROJECT_DIR}/tubearchivist}"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_DIR}/docker-compose.yml}"
BRANCH="${BRANCH:-fork/v0.5.9}"
REMOTE="${REMOTE:-origin}"
ALLOW_DIRTY="${ALLOW_DIRTY:-0}"

log() {
    printf '\n[%s] %s\n' "deploy-server" "$*"
}

fail() {
    printf '\n[%s] ERROR: %s\n' "deploy-server" "$*" >&2
    exit 1
}

require_path() {
    local path="$1"
    local description="$2"
    [[ -e "$path" ]] || fail "$description not found: $path"
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

require_command git
require_command docker

require_path "$PROJECT_DIR" "project directory"
require_path "$REPO_DIR" "repository directory"
require_path "$COMPOSE_FILE" "compose file"
require_path "$REPO_DIR/.git" "git repository metadata"

cd "$REPO_DIR"

CURRENT_BRANCH="$(git branch --show-current)"

if [[ "$ALLOW_DIRTY" != "1" ]] && [[ -n "$(git status --porcelain)" ]]; then
    fail "working tree is dirty in $REPO_DIR. Commit/stash changes or rerun with ALLOW_DIRTY=1"
fi

log "fetching latest refs from $REMOTE"
git fetch "$REMOTE" --prune

if ! git show-ref --verify --quiet "refs/remotes/${REMOTE}/${BRANCH}"; then
    fail "remote branch not found: ${REMOTE}/${BRANCH}"
fi

if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
    log "checking out branch $BRANCH"
    git checkout "$BRANCH"
fi

log "pulling latest code for $BRANCH"
git pull --ff-only "$REMOTE" "$BRANCH"

DEPLOY_COMMIT="$(git rev-parse --short HEAD)"
log "deploying commit $DEPLOY_COMMIT with compose file $COMPOSE_FILE"

docker compose \
    --project-directory "$PROJECT_DIR" \
    -f "$COMPOSE_FILE" \
    up --build -d

log "deployment finished successfully"
