"""Behavior tests for the server deployment script."""

from __future__ import annotations

import fcntl
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "deploy-server.sh"
BRANCH = "fork/v0.5.11"


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

    def run(self, **environment: str) -> subprocess.CompletedProcess:
        """Run the deployment script with optional environment overrides."""
        deploy_environment = self.environment | environment
        return subprocess.run(
            [str(SCRIPT)],
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
    run_command("git", "config", "user.email", "test@example.com", cwd=publisher)
    run_command("git", "config", "user.name", "Test User", cwd=publisher)
    run_command("git", "switch", "-c", BRANCH, cwd=publisher)
    (publisher / "source.txt").write_text("initial\n", encoding="utf-8")
    run_command("git", "add", "source.txt", cwd=publisher)
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
    compose_file.write_text("services: {}\n", encoding="utf-8")

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
if [[ " $* " == *" up "* ]] && [[ "${DOCKER_UP_FAIL:-0}" == "1" ]]; then
    exit 1
fi
if [[ " $* " == *" exec -T tubearchivist curl "* ]] \
    && [[ "${DOCKER_API_FAIL:-0}" == "1" ]]; then
    exit 1
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
    assert build_call.endswith("build --pull")
    assert "--no-cache" not in build_call
    assert "--wait --wait-timeout 300" in up_call
    assert any(
        "exec -T tubearchivist curl --fail --silent --show-error "
        "--max-time 5 http://localhost:8000/api/health/" in call
        for call in calls
    )
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
    (deployment.repository / "source.txt").write_text("dirty\n", encoding="utf-8")

    result = deployment.run()

    assert result.returncode != 0
    assert "working tree is dirty" in result.stderr
    assert not any(" build " in f" {call} " for call in deployment.docker_calls())


def test_rejects_local_ahead_branch(deployment: Deployment) -> None:
    """A clean unpublished commit cannot be deployed."""
    deployment.commit_local()

    result = deployment.run()

    assert result.returncode != 0
    assert "ahead of or diverged" in result.stderr
    assert not any(" build " in f" {call} " for call in deployment.docker_calls())


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
    assert "remote branch not found: origin/fork/v9.9.9" in result.stderr


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
    assert build_call.endswith("build --pull --no-cache")


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


def test_failed_api_probe_reports_service_status(deployment: Deployment) -> None:
    """A responsive Nginx cannot hide an unavailable Django API."""
    result = deployment.run(DOCKER_API_FAIL="1", WAIT_TIMEOUT="1")

    calls = deployment.docker_calls()
    assert result.returncode != 0
    assert any(call.endswith("ps") for call in calls)
    assert "Tube Archivist API did not become ready within 1s" in result.stderr
    assert "deployment finished successfully" not in result.stdout
