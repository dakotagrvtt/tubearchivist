"""Behavior tests for the server deployment script."""

from __future__ import annotations

import fcntl
import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "deploy-server.sh"
BRANCH = "fork/v0.5.12"


def run_command(*args: str | Path, cwd: Path) -> subprocess.CompletedProcess:
    """Run a setup command and require success."""
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


@dataclass
class Deployment:
    """Temporary deployment layout and helpers."""

    project: Path
    repository: Path
    publisher: Path
    docker_log: Path
    environment: dict[str, str]

    def run(
        self, cwd: Path | None = None, **environment: str
    ) -> subprocess.CompletedProcess:
        """Run the deployment script with optional environment overrides."""
        deploy_environment = self.environment | environment
        return subprocess.run(
            [str(SCRIPT)],
            cwd=cwd,
            check=False,
            capture_output=True,
            env=deploy_environment,
            text=True,
            timeout=20,
        )

    def publish(self, content: str = "remote update\n") -> str:
        """Publish a new commit and return its full object ID."""
        source_file = self.publisher / "source.txt"
        source_file.write_text(content, encoding="utf-8")
        run_command("git", "add", "source.txt", cwd=self.publisher)
        run_command("git", "commit", "-m", "remote update", cwd=self.publisher)
        run_command("git", "push", "origin", BRANCH, cwd=self.publisher)
        return run_command(
            "git", "rev-parse", "HEAD", cwd=self.publisher
        ).stdout.strip()

    def commit_local(self, content: str = "local update\n") -> str:
        """Create a commit that exists only in the deployment checkout."""
        source_file = self.repository / "source.txt"
        source_file.write_text(content, encoding="utf-8")
        run_command("git", "add", "source.txt", cwd=self.repository)
        run_command("git", "commit", "-m", "local update", cwd=self.repository)
        return run_command(
            "git", "rev-parse", "HEAD", cwd=self.repository
        ).stdout.strip()

    def docker_calls(self) -> list[str]:
        """Return recorded Docker invocations."""
        if not self.docker_log.exists():
            return []
        return self.docker_log.read_text(encoding="utf-8").splitlines()


@pytest.fixture
def deployment(tmp_path: Path) -> Deployment:
    """Create a remote, publisher, deployment checkout, and fake Docker CLI."""
    origin = tmp_path / "origin.git"
    publisher = tmp_path / "publisher"
    project = tmp_path / "project"
    repository = project / "tubearchivist"
    fake_bin = tmp_path / "bin"
    docker_log = tmp_path / "docker.log"

    origin.mkdir()
    run_command("git", "init", "--bare", cwd=origin)
    run_command("git", "clone", str(origin), str(publisher), cwd=tmp_path)
    run_command(
        "git", "config", "user.email", "test@example.com", cwd=publisher
    )
    run_command("git", "config", "user.name", "Test User", cwd=publisher)
    run_command("git", "switch", "-c", BRANCH, cwd=publisher)
    (publisher / "source.txt").write_text("initial\n", encoding="utf-8")
    (publisher / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    run_command("git", "add", ".", cwd=publisher)
    run_command("git", "commit", "-m", "initial", cwd=publisher)
    run_command("git", "push", "-u", "origin", BRANCH, cwd=publisher)

    project.mkdir()
    run_command(
        "git",
        "clone",
        "--branch",
        BRANCH,
        str(origin),
        str(repository),
        cwd=project,
    )
    run_command(
        "git", "config", "user.email", "test@example.com", cwd=repository
    )
    run_command("git", "config", "user.name", "Test User", cwd=repository)
    compose_file = project / "docker-compose.yml"
    compose_file.write_text(
        json.dumps(
            {
                "name": "deployment-test",
                "services": {
                    "tubearchivist": {
                        "build": {"context": str(repository)},
                        "image": "tubearchivist-local",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$DOCKER_LOG"
if [[ "$*" == "compose version" ]]; then
    exit 0
fi
if [[ "$*" == "compose up --help" ]]; then
    if [[ "${DOCKER_WAIT_SUPPORT:-1}" == "1" ]]; then
        printf '%s\\n' 'Usage: docker compose up [--wait]'
    else
        printf '%s\\n' 'Usage: docker compose up'
    fi
    exit 0
fi
if [[ " $* " == *" config "* ]]; then
    args=("$@")
    for ((i=0; i<${#args[@]}; i++)); do
        if [[ "${args[$i]}" == "-f" ]]; then
            file="${args[$((i+1))]}"
            [[ -f "$file" ]] || exit 1
            if [[ " $* " == *" --format json "* ]]; then
                cat "$file"
            fi
            break
        fi
    done
    exit 0
fi
if [[ "$*" == "image inspect --format {{.Id}} "* ]]; then
    printf '%s\\n' 'sha256:built-image'
    exit 0
fi
if [[ "$*" == "image inspect --format "* ]]; then
    if [[ "${DOCKER_BAD_REVISION:-0}" == "1" ]]; then
        printf '%s\\n' 'stale-revision'
    else
        git -C "$TEST_REPO" rev-parse HEAD
    fi
    exit 0
fi
if [[ " $* " == *" ps --all --quiet tubearchivist "* ]]; then
    printf '%s\\n' 'application-container'
    exit 0
fi
if [[ "$*" == "inspect --format {{.Image}} "* ]]; then
    printf '%s\\n' "${DOCKER_CONTAINER_IMAGE_ID:-sha256:built-image}"
    exit 0
fi
if [[ " $* " == *" up "* ]] && [[ "${DOCKER_UP_FAIL:-0}" == "1" ]]; then
    exit 1
fi
if [[ " $* " == *" build "* ]] && [[ "${DOCKER_BUILD_FAIL:-0}" == "1" ]]; then
    exit 1
fi
if [[ " $* " == *" exec -T tubearchivist curl "* ]] \
    && [[ "${DOCKER_API_FAIL:-0}" == "1" ]]; then
    exit 1
fi
if [[ " $* " == *" inspect ping "* ]]; then
    if [[ "${DOCKER_WORKER_HANG:-0}" == "1" ]]; then
        sleep 30
    fi
    if [[ "${DOCKER_WORKER_FAIL:-0}" == "1" ]]; then
        exit 1
    fi
fi
exit 0
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    environment = os.environ.copy()
    for variable in (
        "PROJECT_DIR",
        "REPO_DIR",
        "COMPOSE_FILE",
        "BRANCH",
        "REMOTE",
        "NO_CACHE",
        "WAIT_TIMEOUT",
        "ALLOW_DIRTY",
        "DOCKER_LOG",
        "DOCKER_WAIT_SUPPORT",
        "DOCKER_UP_FAIL",
        "DOCKER_API_FAIL",
        "DOCKER_BUILD_FAIL",
        "DOCKER_BAD_REVISION",
        "DOCKER_CONTAINER_IMAGE_ID",
        "DOCKER_WORKER_FAIL",
        "DOCKER_WORKER_HANG",
    ):
        environment.pop(variable, None)
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "PROJECT_DIR": str(project),
            "REPO_DIR": str(repository),
            "COMPOSE_FILE": str(compose_file),
            "BRANCH": BRANCH,
            "REMOTE": "origin",
            "DOCKER_LOG": str(docker_log),
            "TEST_REPO": str(repository),
        }
    )
    return Deployment(project, repository, publisher, docker_log, environment)


def test_deploys_exact_remote_commit_with_cached_build(
    deployment: Deployment,
) -> None:
    """The normal path uses cache, waits for health, and reports provenance."""
    result = deployment.run()

    assert result.returncode == 0, result.stderr
    calls = deployment.docker_calls()
    build_call = next(call for call in calls if " build " in f" {call} ")
    up_call = next(
        call
        for call in calls
        if " up " in f" {call} " and "--help" not in call
    )
    assert build_call.endswith("build --pull tubearchivist")
    assert "--no-cache" not in build_call
    assert "--wait --wait-timeout 300" in up_call
    assert "--force-recreate" not in up_call
    assert "--no-build" in up_call
    assert any(
        "exec -T tubearchivist curl --fail --silent --show-error "
        "--max-time 5 http://localhost:8000/api/health/" in call
        for call in calls
    )
    assert f"deployment finished successfully at {BRANCH}@" in result.stdout


def test_default_branch_deploys_current_release(
    deployment: Deployment,
) -> None:
    """An invocation without BRANCH uses the current stable release."""
    deployment.environment.pop("BRANCH")

    result = deployment.run()

    assert result.returncode == 0, result.stderr
    assert f"deployment finished successfully at {BRANCH}@" in result.stdout


def test_fast_forwards_branch_to_remote(deployment: Deployment) -> None:
    """A checkout behind its remote is updated before the build."""
    expected_commit = deployment.publish()

    result = deployment.run()

    actual_commit = run_command(
        "git", "rev-parse", "HEAD", cwd=deployment.repository
    ).stdout.strip()
    assert result.returncode == 0, result.stderr
    assert actual_commit == expected_commit
    assert f"fast-forwarding {BRANCH} to origin/{BRANCH}" in result.stdout


def test_rejects_dirty_checkout(deployment: Deployment) -> None:
    """Uncommitted changes cannot become part of a deployment."""
    (deployment.repository / "source.txt").write_text(
        "dirty\n", encoding="utf-8"
    )

    result = deployment.run()

    assert result.returncode != 0
    assert "working tree is dirty" in result.stderr
    assert not any(
        " build " in f" {call} " for call in deployment.docker_calls()
    )


def test_rejects_local_ahead_branch(deployment: Deployment) -> None:
    """A clean unpublished commit cannot be deployed."""
    deployment.commit_local()

    result = deployment.run()

    assert result.returncode != 0
    assert "ahead of or diverged" in result.stderr
    assert not any(
        " build " in f" {call} " for call in deployment.docker_calls()
    )


def test_rejects_diverged_branch(deployment: Deployment) -> None:
    """The script does not resolve divergent deployment history."""
    deployment.commit_local()
    deployment.publish("different remote update\n")

    result = deployment.run()

    assert result.returncode != 0
    assert "ahead of or diverged" in result.stderr


def test_rejects_missing_remote_branch(deployment: Deployment) -> None:
    """The requested branch must exist on the configured remote."""
    result = deployment.run(BRANCH="fork/v9.9.9")

    assert result.returncode != 0
    assert "unable to fetch origin/fork/v9.9.9" in result.stderr


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"NO_CACHE": "sometimes"}, "NO_CACHE must be 0 or 1"),
        ({"WAIT_TIMEOUT": "0"}, "WAIT_TIMEOUT must be a positive integer"),
        ({"ALLOW_DIRTY": "1"}, "ALLOW_DIRTY is no longer supported"),
    ],
)
def test_rejects_invalid_environment(
    deployment: Deployment, environment: dict[str, str], message: str
) -> None:
    """Unsafe or malformed deployment settings fail before mutation."""
    result = deployment.run(**environment)

    assert result.returncode != 0
    assert message in result.stderr


def test_no_cache_build_is_opt_in(deployment: Deployment) -> None:
    """NO_CACHE adds the clean-build flag without changing other behavior."""
    result = deployment.run(NO_CACHE="1")

    build_call = next(
        call for call in deployment.docker_calls() if " build " in f" {call} "
    )
    assert result.returncode == 0, result.stderr
    assert build_call.endswith("build --pull --no-cache tubearchivist")


def test_requires_compose_wait_support(deployment: Deployment) -> None:
    """Old Compose clients fail before the repository is updated."""
    result = deployment.run(DOCKER_WAIT_SUPPORT="0")

    assert result.returncode != 0
    assert "docker compose up must support --wait" in result.stderr


def test_rejects_concurrent_deployment(deployment: Deployment) -> None:
    """The project lock prevents overlapping Git and Compose operations."""
    lock_path = deployment.project / ".deploy-server.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = deployment.run()

    assert result.returncode != 0
    assert "another deployment is already running" in result.stderr


def test_failed_health_wait_reports_service_status(
    deployment: Deployment,
) -> None:
    """A failed wait prints Compose status and never reports success."""
    result = deployment.run(DOCKER_UP_FAIL="1", WAIT_TIMEOUT="45")

    calls = deployment.docker_calls()
    assert result.returncode != 0
    assert any(call.endswith("ps") for call in calls)
    assert "containers did not become ready within 45s" in result.stderr
    assert "deployment finished successfully" not in result.stdout


def test_failed_api_probe_reports_service_status(
    deployment: Deployment,
) -> None:
    """A responsive Nginx cannot hide an unavailable Django API."""
    result = deployment.run(DOCKER_API_FAIL="1", WAIT_TIMEOUT="1")

    calls = deployment.docker_calls()
    assert result.returncode != 0
    assert any(call.endswith("ps") for call in calls)
    assert "Tube Archivist API did not become ready within 1s" in result.stderr
    assert "deployment finished successfully" not in result.stdout


@pytest.mark.parametrize("keep_tracking_ref", [False, True])
def test_fetches_release_despite_restricted_refspec(
    deployment: Deployment, keep_tracking_ref: bool
) -> None:
    """Fetch the requested release even with old single-branch settings."""
    run_command(
        "git",
        "push",
        "origin",
        "HEAD:refs/heads/fork/v0.5.11",
        cwd=deployment.publisher,
    )
    run_command(
        "git",
        "config",
        "--replace-all",
        "remote.origin.fetch",
        "+refs/heads/fork/v0.5.11:refs/remotes/origin/fork/v0.5.11",
        cwd=deployment.repository,
    )
    if not keep_tracking_ref:
        run_command(
            "git",
            "update-ref",
            "-d",
            f"refs/remotes/origin/{BRANCH}",
            cwd=deployment.repository,
        )
    expected = deployment.publish()

    result = deployment.run()

    assert result.returncode == 0, result.stderr
    actual = run_command(
        "git", "rev-parse", "HEAD", cwd=deployment.repository
    ).stdout.strip()
    assert actual == expected


def test_relative_paths_resolve_from_invocation_directory(
    deployment: Deployment,
) -> None:
    """Changing to the checkout must not change Compose path resolution."""
    result = deployment.run(
        cwd=deployment.project,
        PROJECT_DIR=".",
        REPO_DIR="./tubearchivist",
        COMPOSE_FILE="./docker-compose.yml",
    )

    assert result.returncode == 0, result.stderr
    assert any(
        f"--project-directory {deployment.project} " in call
        for call in deployment.docker_calls()
    )


def test_upgrades_single_branch_clone(deployment: Deployment) -> None:
    """Switch to a release missing from both local heads and fetch settings."""
    old_branch = "fork/v0.5.11"
    run_command(
        "git",
        "push",
        "origin",
        f"HEAD:refs/heads/{old_branch}",
        cwd=deployment.publisher,
    )
    run_command("git", "switch", "-c", old_branch, cwd=deployment.repository)
    run_command("git", "branch", "-D", BRANCH, cwd=deployment.repository)
    run_command(
        "git",
        "update-ref",
        "-d",
        f"refs/remotes/origin/{BRANCH}",
        cwd=deployment.repository,
    )
    run_command(
        "git",
        "config",
        "--replace-all",
        "remote.origin.fetch",
        f"+refs/heads/{old_branch}:refs/remotes/origin/{old_branch}",
        cwd=deployment.repository,
    )
    expected = deployment.publish()

    result = deployment.run()

    assert result.returncode == 0, result.stderr
    assert (
        run_command(
            "git", "branch", "--show-current", cwd=deployment.repository
        ).stdout.strip()
        == BRANCH
    )
    assert (
        run_command(
            "git", "rev-parse", "HEAD", cwd=deployment.repository
        ).stdout.strip()
        == expected
    )


def test_project_directory_can_be_repository(deployment: Deployment) -> None:
    """The deployment lock must not dirty an otherwise clean checkout."""
    result = deployment.run(PROJECT_DIR=str(deployment.repository))

    assert result.returncode == 0, result.stderr
    assert not run_command(
        "git", "status", "--porcelain", cwd=deployment.repository
    ).stdout


@pytest.mark.parametrize(
    "build",
    [
        None,
        {"context": "/wrong/checkout"},
        {"dockerfile": "other.Dockerfile"},
        {"dockerfile_inline": "FROM scratch"},
        {"target": "node-builder"},
    ],
)
def test_rejects_application_without_checkout_build(
    deployment: Deployment, build: dict | None
) -> None:
    """An image-only or unrelated build cannot represent the release."""
    compose_file = deployment.project / "docker-compose.yml"
    config = json.loads(compose_file.read_text())
    app = config["services"]["tubearchivist"]
    if build is None:
        app.pop("build")
    else:
        app["build"].update(build)
    compose_file.write_text(json.dumps(config))

    result = deployment.run()

    assert result.returncode != 0
    assert "build" in result.stderr
    assert not any(" build " in f" {c} " for c in deployment.docker_calls())


@pytest.mark.parametrize("target", ["/app", "/app/run.sh", "/"])
def test_rejects_mounts_over_application_code(
    deployment: Deployment, target: str
) -> None:
    """Mounts must not replace the application after image verification."""
    compose_file = deployment.project / "docker-compose.yml"
    config = json.loads(compose_file.read_text())
    config["services"]["tubearchivist"]["volumes"] = [
        {"type": "bind", "source": "/old/code", "target": target}
    ]
    compose_file.write_text(json.dumps(config))

    result = deployment.run()

    assert result.returncode != 0
    assert "mount" in result.stderr
    assert not any(" build " in f" {c} " for c in deployment.docker_calls())


def test_rejects_image_with_wrong_revision(deployment: Deployment) -> None:
    """An incorrectly labelled build must fail before changing containers."""
    result = deployment.run(DOCKER_BAD_REVISION="1")

    assert result.returncode != 0
    assert "revision" in result.stderr
    assert not any(" up -d " in c for c in deployment.docker_calls())


def test_rejects_running_image_mismatch(deployment: Deployment) -> None:
    """A healthy but different image cannot produce a success report."""
    result = deployment.run(DOCKER_CONTAINER_IMAGE_ID="sha256:old-image")

    assert result.returncode != 0
    assert "running image" in result.stderr
    assert "deployment finished successfully" not in result.stdout


def test_checks_worker_in_deployed_container(deployment: Deployment) -> None:
    """Another worker sharing Redis must not satisfy this container's check."""
    result = deployment.run()

    assert result.returncode == 0, result.stderr
    calls = deployment.docker_calls()
    worker_call = next(c for c in calls if "inspect ping" in c)
    assert '--destination "celery@$(hostname)"' in worker_call


@pytest.mark.parametrize(
    "failure", ["DOCKER_WORKER_FAIL", "DOCKER_WORKER_HANG"]
)
def test_worker_failure_is_bounded_and_reports_status(
    deployment: Deployment, failure: str
) -> None:
    """An unavailable or hanging worker probe cannot report success."""
    result = deployment.run(WAIT_TIMEOUT="2", **{failure: "1"})

    assert result.returncode != 0
    assert "Celery worker" in result.stderr
    assert any(c.endswith("ps") for c in deployment.docker_calls())
    assert "deployment finished successfully" not in result.stdout


@pytest.mark.parametrize("build_failure", ["0", "1"])
def test_override_is_cleaned_without_changing_server_compose(
    deployment: Deployment, build_failure: str
) -> None:
    """Success and build failure both remove the temporary image override."""
    compose_file = deployment.project / "docker-compose.yml"
    original = compose_file.read_bytes()

    result = deployment.run(DOCKER_BUILD_FAIL=build_failure)

    assert (result.returncode != 0) == (build_failure == "1")
    build_call = next(
        c for c in deployment.docker_calls() if " build " in f" {c} "
    )
    arguments = shlex.split(build_call)
    files = [
        arguments[i + 1] for i, arg in enumerate(arguments) if arg == "-f"
    ]
    assert len(files) == 2
    assert not Path(files[1]).exists()
    assert compose_file.read_bytes() == original
    if build_failure == "1":
        assert not any(" up -d " in c for c in deployment.docker_calls())


def test_release_override_with_real_compose(tmp_path: Path) -> None:
    """Pin the release build while preserving the server's Compose settings."""
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker Compose CLI is not installed")
    version = subprocess.run(
        [docker, "compose", "version"], capture_output=True, check=False
    )
    if version.returncode:
        pytest.skip("Docker Compose plugin is not installed")
    repository = tmp_path / "checkout"
    repository.mkdir()
    (repository / "Dockerfile").write_text("FROM scratch\n")
    config = {
        "name": "contract-test",
        "services": {
            "tubearchivist": {
                "build": {
                    "context": "./checkout",
                    "args": {"INSTALL_DEBUG": "1"},
                },
                "image": "original-image",
                "pull_policy": "always",
                "environment": {"TEST_LITERAL": "a$$b"},
                "volumes": ["media:/youtube", "cache:/cache"],
                "ports": ["127.0.0.1:8000:8000"],
            },
            "redis": {"image": "redis:7"},
        },
        "volumes": {"media": {}, "cache": {}},
    }
    compose_file = tmp_path / "compose.json"
    compose_file.write_text(json.dumps(config))
    base_args = [
        docker,
        "compose",
        "--project-directory",
        str(tmp_path),
        "-f",
        str(compose_file),
    ]
    resolved = run_command(
        *base_args, "config", "--format", "json", cwd=tmp_path
    ).stdout
    override = tmp_path / "release.json"
    revision = "a" * 40
    helper = subprocess.run(
        [
            "python3",
            str(SCRIPT.parent / "deploy_config.py"),
            str(repository),
            revision,
            str(override),
        ],
        input=resolved,
        text=True,
        capture_output=True,
        check=False,
    )
    assert helper.returncode == 0, helper.stderr
    merged = json.loads(
        run_command(
            *base_args,
            "-f",
            override,
            "config",
            "--format",
            "json",
            cwd=tmp_path,
        ).stdout
    )
    application = merged["services"]["tubearchivist"]
    original = json.loads(resolved)
    assert (
        application["image"]
        == f"tubearchivist-deploy-contract-test:{revision}"
    )
    assert helper.stdout.strip() == application["image"]
    assert application["pull_policy"] == "never"
    assert application["build"]["context"] == str(repository)
    assert (
        application["build"]["labels"]["org.opencontainers.image.revision"]
        == revision
    )
    assert application["build"]["args"] == {"INSTALL_DEBUG": "1"}
    for field in ("environment", "volumes", "ports"):
        assert (
            application[field] == original["services"]["tubearchivist"][field]
        )
    assert merged["services"]["redis"] == original["services"]["redis"]
    assert merged["volumes"] == original["volumes"]


def test_branch_switch_can_remove_deployment_helpers(
    deployment: Deployment,
) -> None:
    """Keep the running script and helper paired when switching releases."""
    old_branch = "fork/v0.5.11"
    run_command(
        "git",
        "push",
        "origin",
        f"HEAD:refs/heads/{old_branch}",
        cwd=deployment.publisher,
    )
    scripts = deployment.publisher / "scripts"
    scripts.mkdir()
    shutil.copy2(SCRIPT, scripts / SCRIPT.name)
    shutil.copy2(
        SCRIPT.parent / "deploy_config.py", scripts / "deploy_config.py"
    )
    run_command("git", "add", "scripts", cwd=deployment.publisher)
    deployment.publish()
    run_command("git", "pull", "--ff-only", cwd=deployment.repository)

    result = subprocess.run(
        [str(deployment.repository / "scripts" / SCRIPT.name)],
        env=deployment.environment | {"BRANCH": old_branch},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not (deployment.repository / "scripts/deploy_config.py").exists()
    assert (
        f"deployment finished successfully at {old_branch}@" in result.stdout
    )
