"""Run a disposable, locally bound Supervisor/App smoke lab from the host.

The images are pinned to the digests exercised on 2026-10-04. This helper
does not create a Home Assistant user or remove persistent Docker volumes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


PROJECT = Path(__file__).resolve().parents[1]
CONTAINER = "symphonia-ha-lab"
SUPERVISOR_VOLUME = "symphonia-ha-lab-supervisor"
DEVCONTAINER_IMAGE = (
    "ghcr.io/home-assistant/devcontainer@"
    "sha256:81ea6e6892125d08e88b5a873c12da00131dfc3a184d335179576ec60bc0ecb0"
)
STAGING_IMAGE = (
    "docker.io/library/python@"
    "sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d"
)


def container_command(project: Path = PROJECT) -> list[str]:
    """Use separate durable volumes and loopback-only host ports."""
    return [
        "docker", "run", "--detach", "--name", CONTAINER,
        "--hostname", CONTAINER, "--privileged", "--pull", "never",
        "--label", "org.vypdev.symphonia.lab=ha-app",
        "--publish", "127.0.0.1:7123:80",
        "--publish", "127.0.0.1:7357:4357",
        "--env", "WORKSPACE_DIRECTORY=/workspaces/symphonia",
        "--env", "SUPERVISOR_CHANNEL=beta",
        "--mount", f"type=bind,source={project},target=/workspaces/symphonia,readonly",
        "--mount", "type=volume,source=symphonia-ha-lab-docker,target=/var/lib/docker",
        "--mount", "type=volume,source=symphonia-ha-lab-containerd,target=/var/lib/containerd",
        "--mount", f"type=volume,source={SUPERVISOR_VOLUME},target=/mnt/supervisor",
        "--mount", "type=tmpfs,target=/tmp",
        DEVCONTAINER_IMAGE,
    ]


def stage_command(project: Path = PROJECT) -> list[str]:
    """Run the existing guarded staging helper against the shared volume."""
    return [
        "docker", "run", "--rm", "--network", "none", "--pull", "never",
        "--mount", f"type=bind,source={project},target=/workspaces/symphonia,readonly",
        "--mount", f"type=volume,source={SUPERVISOR_VOLUME},target=/mnt/supervisor",
        "--workdir", "/workspaces/symphonia", STAGING_IMAGE,
        "python", "tools/stage_ha_local_app.py",
    ]


def app_is_installed(data: dict[str, object]) -> bool:
    """Normalize the store and installed-App detail response shapes."""
    return data.get("version") is not None


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True, timeout=600, check=False)
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Docker lab command failed: {detail}")
    return result


def _json(*args: str) -> dict[str, object]:
    result = _run(*args)
    response = json.loads(result.stdout)
    if not isinstance(response, dict) or response.get("result") != "ok":
        raise RuntimeError("Supervisor did not return a successful response")
    return response


def _ensure_image(image: str) -> None:
    if _run("docker", "image", "inspect", image, check=False).returncode:
        print(f"Pulling pinned image {image}", flush=True)
        _run("docker", "pull", image)


def _container_details() -> dict[str, str] | None:
    result = _run(
        "docker", "inspect", CONTAINER,
        "--format", "{{json .Config.Image}} {{.State.Running}} {{index .Config.Labels \"org.vypdev.symphonia.lab\"}}",
        check=False,
    )
    if result.returncode:
        return None
    image, running, label = result.stdout.strip().split(" ", 2)
    return {"image": json.loads(image), "running": running, "label": label}


def _start_container() -> None:
    _ensure_image(DEVCONTAINER_IMAGE)
    details = _container_details()
    if details is None:
        print("Creating isolated Supervisor devcontainer", flush=True)
        _run(*container_command())
    elif details["image"] != DEVCONTAINER_IMAGE or details["label"] != "ha-app":
        raise RuntimeError(f"Refusing to reuse an unrelated container named {CONTAINER}")
    elif details["running"] != "true":
        print("Starting existing Supervisor devcontainer", flush=True)
        _run("docker", "start", CONTAINER)


def _stage() -> None:
    _ensure_image(STAGING_IMAGE)
    print("Staging checked-out App source into its own Supervisor volume", flush=True)
    _run(*stage_command())


def _supervisor_ready() -> bool:
    result = _run("docker", "exec", CONTAINER, "ha", "supervisor", "info", "--raw-json", check=False)
    if result.returncode:
        return False
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return isinstance(response, dict) and response.get("result") == "ok"


def _start_supervisor() -> None:
    result = _run(
        "docker", "exec", CONTAINER, "docker", "inspect", "hassio_supervisor",
        "--format", "{{.State.Running}}", check=False,
    )
    if result.stdout.strip() != "true":
        print("Starting Supervisor; the first run downloads Home Assistant images", flush=True)
        environment = "SUPERVISOR_UNCONFINED=1 " if sys.platform == "darwin" else ""
        command = f"{environment}supervisor_run > /mnt/supervisor/symphonia-supervisor-start.log 2>&1"
        _run("docker", "exec", "--detach", CONTAINER, "sh", "-lc", command)
    deadline = time.monotonic() + 480
    while time.monotonic() < deadline:
        if _supervisor_ready():
            return
        time.sleep(3)
    raise RuntimeError("Supervisor did not become ready; inspect the lab startup log")


def _install_app() -> None:
    _json("docker", "exec", CONTAINER, "ha", "store", "reload", "--raw-json")
    response = _json("docker", "exec", CONTAINER, "ha", "apps", "info", "local_symphonia", "--raw-json")
    data = response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Symphonia was not discovered as a local App")
    # The installed-App detail endpoint reports a version/state but omits the
    # `installed` boolean used by the store's available-App detail response.
    if app_is_installed(data):
        print("Rebuilding installed Symphonia App from staged source", flush=True)
        _json("docker", "exec", CONTAINER, "ha", "apps", "rebuild", "--force", "local_symphonia", "--raw-json")
    else:
        print("Installing Symphonia App from staged source", flush=True)
        _json("docker", "exec", CONTAINER, "ha", "apps", "install", "local_symphonia", "--raw-json")
    _json("docker", "exec", CONTAINER, "ha", "apps", "start", "local_symphonia", "--raw-json")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        result = _run(
            "docker", "exec", CONTAINER, "docker", "inspect", "app_local_symphonia",
            "--format", "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
            check=False,
        )
        if result.stdout.strip() == "running healthy":
            return
        time.sleep(2)
    raise RuntimeError("Symphonia did not become healthy; inspect its App logs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("up", "stage", "status", "stop"))
    args = parser.parse_args()
    try:
        if args.command == "up":
            _start_container()
            _stage()
            _start_supervisor()
            _install_app()
            print("App healthy. Home Assistant onboarding: http://127.0.0.1:7123/", flush=True)
        elif args.command == "stage":
            _stage()
        elif args.command == "status":
            details = _container_details()
            print("Lab container: absent" if details is None else f"Lab container: {'running' if details['running'] == 'true' else 'stopped'}")
            if details and details["running"] == "true":
                print(f"Supervisor API ready: {_supervisor_ready()}")
        else:
            details = _container_details()
            if details is not None and details["label"] != "ha-app":
                raise RuntimeError(f"Refusing to stop an unrelated container named {CONTAINER}")
            if details is not None:
                _run("docker", "stop", CONTAINER)
            print("Lab stopped; named volumes retained")
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
