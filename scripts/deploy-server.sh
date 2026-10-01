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
BRANCH="${BRANCH:-fork/v0.5.12}"
REMOTE="${REMOTE:-origin}"
NO_CACHE="${NO_CACHE:-0}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-300}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

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
    docker compose "${COMPOSE_ARGS[@]}" "$@"
}

report_startup_failure() {
    local message="$1"

    log "container status after failed startup"
    compose ps || true
    fail "$message"
}

wait_for_probe() {
    local description="$1"
    shift
    local remaining probe_timeout

    log "verifying $description"
    while true; do
        remaining=$((READINESS_DEADLINE - SECONDS))
        if ((remaining <= 0)); then
            report_startup_failure \
                "$description did not become ready within ${WAIT_TIMEOUT}s"
        fi
        probe_timeout=10
        if ((remaining < probe_timeout)); then
            probe_timeout="$remaining"
        fi
        if timeout --kill-after=1 "${probe_timeout}s" \
            docker compose "${COMPOSE_ARGS[@]}" exec -T tubearchivist \
            "$@" >/dev/null; then
            return
        fi
        remaining=$((READINESS_DEADLINE - SECONDS))
        if ((remaining > 2)); then
            sleep 2
        elif ((remaining > 0)); then
            sleep "$remaining"
        fi
    done
}

require_command git
require_command docker
require_command flock
require_command realpath
require_command python3
require_command timeout

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
require_path "$SCRIPT_DIR/deploy_config.py" "deployment config helper"

PROJECT_DIR="$(realpath -e -- "$PROJECT_DIR")"
REPO_DIR="$(realpath -e -- "$REPO_DIR")"
COMPOSE_FILE="$(realpath -e -- "$COMPOSE_FILE")"
COMPOSE_ARGS=(--project-directory "$PROJECT_DIR" -f "$COMPOSE_FILE")

LOCK_FILE="${PROJECT_DIR}/.deploy-server.lock"
case "$PROJECT_DIR/" in
    "$REPO_DIR/"*)
        LOCK_FILE="$(git -C "$REPO_DIR" rev-parse --absolute-git-dir)/deploy-server.lock"
        ;;
esac
if ! exec 9>"$LOCK_FILE"; then
    fail "unable to open deployment lock: $LOCK_FILE"
fi
flock -n 9 || fail "another deployment is already running for $PROJECT_DIR"

# Preserve this script's helper across a fetch or switch to an older release.
DEPLOY_TMP="$(mktemp -d)"
trap 'rm -rf -- "$DEPLOY_TMP"' EXIT
cp -- "$SCRIPT_DIR/deploy_config.py" "$DEPLOY_TMP/deploy_config.py"

cd "$REPO_DIR"

git remote get-url "$REMOTE" >/dev/null 2>&1 \
    || fail "git remote not found: $REMOTE"
git check-ref-format --branch "$BRANCH" >/dev/null 2>&1 \
    || fail "invalid branch name: $BRANCH"

if [[ -n "$(git status --porcelain)" ]]; then
    fail "working tree is dirty in $REPO_DIR; commit or stash changes before deploying"
fi

log "fetching latest refs from $REMOTE"
REMOTE_REF="refs/remotes/${REMOTE}/${BRANCH}"
if ! git fetch --no-tags "$REMOTE" "+refs/heads/${BRANCH}:${REMOTE_REF}"; then
    fail "unable to fetch ${REMOTE}/${BRANCH}; check remote access and branch name"
fi
if ! git show-ref --verify --quiet "$REMOTE_REF"; then
    fail "remote branch not found: ${REMOTE}/${BRANCH}"
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
    log "checking out branch $BRANCH"
    if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
        git switch "$BRANCH"
    else
        # A restricted remote fetch refspec may not recognize this ref as
        # a tracking branch. Every deployment fetches it explicitly anyway.
        git switch --no-track -c "$BRANCH" "$REMOTE_REF"
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

DEPLOY_COMMIT="$LOCAL_COMMIT"
log "deploying commit $DEPLOY_COMMIT with compose file $COMPOSE_FILE"

log "validating compose file"
compose config --quiet
OVERRIDE_FILE="${DEPLOY_TMP}/release.json"
DEPLOY_IMAGE="$(compose config --format json | python3 \
    "$DEPLOY_TMP/deploy_config.py" "$REPO_DIR" "$DEPLOY_COMMIT" "$OVERRIDE_FILE")"
COMPOSE_ARGS+=(-f "$OVERRIDE_FILE")
compose config --quiet

BUILD_ARGS=(build --pull)
if [[ "$NO_CACHE" == "1" ]]; then
    BUILD_ARGS+=(--no-cache)
    log "building Docker images without cache"
else
    log "building Docker images with cache"
fi
compose "${BUILD_ARGS[@]}" tubearchivist

BUILT_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$DEPLOY_IMAGE")"
BUILT_REVISION="$(docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
    "$DEPLOY_IMAGE")"
[[ -n "$BUILT_IMAGE_ID" && "$BUILT_REVISION" == "$DEPLOY_COMMIT" ]] \
    || fail "built image revision does not match $DEPLOY_COMMIT"

log "starting containers and waiting up to ${WAIT_TIMEOUT}s for health"
READINESS_DEADLINE=$((SECONDS + WAIT_TIMEOUT))
if ! compose up -d --no-build --remove-orphans \
    --wait --wait-timeout "$WAIT_TIMEOUT"; then
    report_startup_failure \
        "containers did not become ready within ${WAIT_TIMEOUT}s"
fi

CONTAINER_ID="$(compose ps --all --quiet tubearchivist)"
[[ -n "$CONTAINER_ID" && "$CONTAINER_ID" != *$'\n'* ]] \
    || report_startup_failure "expected exactly one Tube Archivist container"
RUNNING_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$CONTAINER_ID")"
[[ "$RUNNING_IMAGE_ID" == "$BUILT_IMAGE_ID" ]] \
    || report_startup_failure "running image does not match the built release image"

wait_for_probe "Tube Archivist API" curl --fail --silent --show-error \
    --max-time 5 "http://localhost:8000/api/health/"
wait_for_probe "Celery worker" sh -c \
    'exec celery -A task.celery inspect ping --timeout 2 --destination "celery@$(hostname)"'

compose ps

log "deployment finished successfully at ${BRANCH}@${DEPLOY_COMMIT} (${BUILT_IMAGE_ID})"
