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
#   PROJECT_DIR, REPO_DIR, COMPOSE_FILE, BRANCH, REMOTE, NO_CACHE,
#   WAIT_TIMEOUT

PROJECT_DIR="${PROJECT_DIR:-/zpool-8TB/containers/tubearchivist}"
REPO_DIR="${REPO_DIR:-${PROJECT_DIR}/tubearchivist}"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_DIR}/docker-compose.yml}"
BRANCH="${BRANCH:-fork/v0.5.10}"
REMOTE="${REMOTE:-origin}"
NO_CACHE="${NO_CACHE:-0}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-300}"

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

compose() {
    docker compose \
        --project-directory "$PROJECT_DIR" \
        -f "$COMPOSE_FILE" \
        "$@"
}

report_startup_failure() {
    local message="$1"

    log "container status after failed startup"
    compose ps || true
    fail "$message"
}

require_command git
require_command docker
require_command flock

if [[ -n "${ALLOW_DIRTY:-}" ]]; then
    fail "ALLOW_DIRTY is no longer supported; deployments require a clean working tree"
fi

case "$NO_CACHE" in
    0 | 1) ;;
    *) fail "NO_CACHE must be 0 or 1, got: $NO_CACHE" ;;
esac

if [[ ! "$WAIT_TIMEOUT" =~ ^[1-9][0-9]*$ ]]; then
    fail "WAIT_TIMEOUT must be a positive integer, got: $WAIT_TIMEOUT"
fi

docker compose version >/dev/null 2>&1 || fail "docker compose plugin not available"

COMPOSE_UP_HELP="$(docker compose up --help 2>/dev/null)" \
    || fail "unable to inspect docker compose up options"
[[ "$COMPOSE_UP_HELP" == *"--wait"* ]] \
    || fail "docker compose up must support --wait"

require_path "$PROJECT_DIR" "project directory"
require_path "$REPO_DIR" "repository directory"
require_path "$COMPOSE_FILE" "compose file"
require_path "$REPO_DIR/.git" "git repository metadata"

LOCK_FILE="${PROJECT_DIR}/.deploy-server.lock"
if ! exec 9>"$LOCK_FILE"; then
    fail "unable to open deployment lock: $LOCK_FILE"
fi
flock -n 9 || fail "another deployment is already running for $PROJECT_DIR"

cd "$REPO_DIR"

git remote get-url "$REMOTE" >/dev/null 2>&1 \
    || fail "git remote not found: $REMOTE"
git check-ref-format --branch "$BRANCH" >/dev/null 2>&1 \
    || fail "invalid branch name: $BRANCH"

if [[ -n "$(git status --porcelain)" ]]; then
    fail "working tree is dirty in $REPO_DIR; commit or stash changes before deploying"
fi

log "fetching latest refs from $REMOTE"
git fetch "$REMOTE" --prune

REMOTE_REF="refs/remotes/${REMOTE}/${BRANCH}"
if ! git show-ref --verify --quiet "$REMOTE_REF"; then
    fail "remote branch not found: ${REMOTE}/${BRANCH}"
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
    log "checking out branch $BRANCH"
    if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
        git switch "$BRANCH"
    else
        git switch --track -c "$BRANCH" "${REMOTE}/${BRANCH}"
    fi
fi

LOCAL_COMMIT="$(git rev-parse HEAD)"
REMOTE_COMMIT="$(git rev-parse "${REMOTE_REF}^{commit}")"

if [[ "$LOCAL_COMMIT" != "$REMOTE_COMMIT" ]]; then
    if git merge-base --is-ancestor HEAD "$REMOTE_REF"; then
        log "fast-forwarding $BRANCH to ${REMOTE}/${BRANCH}"
        git merge --ff-only "$REMOTE_REF"
    else
        fail "local $BRANCH is ahead of or diverged from ${REMOTE}/${BRANCH}"
    fi
fi

LOCAL_COMMIT="$(git rev-parse HEAD)"
[[ "$LOCAL_COMMIT" == "$REMOTE_COMMIT" ]] \
    || fail "local HEAD does not match ${REMOTE}/${BRANCH} after update"

DEPLOY_COMMIT="$(git rev-parse --short HEAD)"
log "deploying commit $DEPLOY_COMMIT with compose file $COMPOSE_FILE"

log "validating compose file"
compose config --quiet

BUILD_ARGS=(build --pull)
if [[ "$NO_CACHE" == "1" ]]; then
    BUILD_ARGS+=(--no-cache)
    log "building Docker images without cache"
else
    log "building Docker images with cache"
fi
compose "${BUILD_ARGS[@]}"

log "starting containers and waiting up to ${WAIT_TIMEOUT}s for health"
READINESS_DEADLINE=$((SECONDS + WAIT_TIMEOUT))
if ! compose up -d --force-recreate --remove-orphans \
    --wait --wait-timeout "$WAIT_TIMEOUT"; then
    report_startup_failure \
        "containers did not become ready within ${WAIT_TIMEOUT}s"
fi

log "verifying the Tube Archivist API"
API_HEALTH_URL="http://localhost:8000/api/health/"
while true; do
    REMAINING_TIME=$((READINESS_DEADLINE - SECONDS))
    if ((REMAINING_TIME <= 0)); then
        report_startup_failure \
            "Tube Archivist API did not become ready within ${WAIT_TIMEOUT}s"
    fi

    CURL_TIMEOUT=5
    if ((REMAINING_TIME < CURL_TIMEOUT)); then
        CURL_TIMEOUT="$REMAINING_TIME"
    fi

    if compose exec -T tubearchivist curl --fail --silent --show-error \
        --max-time "$CURL_TIMEOUT" "$API_HEALTH_URL" >/dev/null; then
        break
    fi

    REMAINING_TIME=$((READINESS_DEADLINE - SECONDS))
    if ((REMAINING_TIME <= 0)); then
        report_startup_failure \
            "Tube Archivist API did not become ready within ${WAIT_TIMEOUT}s"
    fi

    if ((REMAINING_TIME > 2)); then
        sleep 2
    else
        sleep "$REMAINING_TIME"
    fi
done

compose ps

log "deployment finished successfully at ${BRANCH}@${DEPLOY_COMMIT}"
