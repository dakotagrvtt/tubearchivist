"""Validate the release build and create a small Compose image override."""

import json
import posixpath
import sys
from pathlib import Path


def release_override(config, repository, revision):
    """Bind the application image to the validated checkout and revision."""
    application = config.get("services", {}).get("tubearchivist", {})
    build = application.get("build")
    if not isinstance(build, dict) or not build.get("context"):
        raise ValueError("tubearchivist must build from REPO_DIR")
    context = Path(build["context"]).resolve()
    if context != repository:
        raise ValueError("tubearchivist build context must match REPO_DIR")
    dockerfile = context / build.get("dockerfile", "Dockerfile")
    if (
        "dockerfile_inline" in build
        or dockerfile.resolve() != repository / "Dockerfile"
        or build.get("target") not in (None, "tubearchivist")
    ):
        raise ValueError(
            "tubearchivist must build the repository Dockerfile's final stage"
        )
    for volume in application.get("volumes", []):
        target = posixpath.normpath(volume["target"])
        if target in ("/", "/app") or target.startswith("/app/"):
            raise ValueError("tubearchivist mounts must not replace /app code")

    image = f"tubearchivist-deploy-{config['name']}:{revision}"
    return {
        "services": {
            "tubearchivist": {
                "image": image,
                "pull_policy": "never",
                "build": {
                    "labels": {"org.opencontainers.image.revision": revision}
                },
            }
        }
    }


def main():
    """Read resolved Compose JSON without copying secrets into the override."""
    repository, revision, output = sys.argv[1:]
    try:
        override = release_override(
            json.load(sys.stdin), Path(repository).resolve(), revision
        )
    except (ValueError, KeyError) as error:
        sys.exit(f"[deploy-server] ERROR: invalid deployment config: {error}")
    Path(output).write_text(json.dumps(override) + "\n", encoding="utf-8")
    print(override["services"]["tubearchivist"]["image"])


if __name__ == "__main__":
    main()
