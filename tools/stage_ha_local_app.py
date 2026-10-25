"""Stage the repository's nested App scaffold for Home Assistant's Apps devcontainer."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any


MANIFEST_NAME = ".symphonia-devcontainer-stage.json"
DEFAULT_TARGET = Path("/mnt/supervisor/apps/local/symphonia")
IMAGE_LINE = re.compile(r"^image:\s*[^\r\n]*(?:\r?\n|$)", re.MULTILINE)


def _safe_relative_path(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("staging manifest paths must be strings")
    path = PurePosixPath(value)
    invalid_path = (
        not value,
        path.is_absolute(),
        path.as_posix() == ".",
        ".." in path.parts,
        "\\" in value,
        value == MANIFEST_NAME,
    )
    if any(invalid_path):
        raise ValueError(f"unsafe staging manifest path: {value!r}")
    return path.as_posix()


def _read_manifest(marker: Path) -> set[str]:
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("staging manifest must be a regular file")
    try:
        manifest = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("staging manifest is unreadable or invalid") from error
    paths = manifest.get("managed_files") if isinstance(manifest, dict) else None
    if not isinstance(paths, list):
        raise ValueError("staging manifest must contain a managed_files list")
    return {_safe_relative_path(path) for path in paths}


def _managed_files(target: Path) -> set[str]:
    if not target.exists():
        return set()
    if not target.is_dir() or target.is_symlink():
        raise ValueError(f"staging target is not a regular directory: {target}")
    marker = target / MANIFEST_NAME
    if marker.exists() or marker.is_symlink():
        return _read_manifest(marker)
    if any(target.iterdir()):
        raise ValueError(f"refusing to overwrite an unowned App directory: {target}")
    return set()


def _ensure_no_symlink_parents(target: Path, relative: str) -> None:
    current = target
    for part in PurePosixPath(relative).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"refusing to traverse staged symlink: {current}")
        if current.exists() and not current.is_dir():
            raise ValueError(f"staged parent is not a directory: {current}")


def _source_files(source: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for path in source.rglob("*"):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"source App tree must not contain symlinks: {path}")
        if path.is_file():
            result[path.relative_to(source.parent).as_posix()] = path.read_bytes()
    return result


def _resolve_target(project: Path, target: Path) -> Path:
    raw_destination = Path(os.path.abspath(target))
    if raw_destination.is_symlink():
        raise ValueError("staging target must not be a symlink")
    destination = raw_destination.resolve()
    if destination == project or destination in project.parents:
        raise ValueError("staging target must be outside the source repository")
    if project in destination.parents:
        raise ValueError("staging target must be outside the source repository")
    return destination


def _desired_files(project: Path) -> dict[str, bytes]:
    metadata = project / "addon" / "config.yaml"
    dockerfile = project / "Dockerfile"
    source = project / "src"
    if not metadata.is_file() or not dockerfile.is_file() or not source.is_dir():
        raise ValueError("expected addon/config.yaml, Dockerfile, and src/ in project")

    config = metadata.read_text(encoding="utf-8")
    config, removed = IMAGE_LINE.subn("", config, count=1)
    if removed != 1:
        raise ValueError("expected exactly one top-level image setting in App metadata")

    return {
        "config.yaml": config.encode("utf-8"),
        "Dockerfile": dockerfile.read_bytes(),
        **_source_files(source),
    }


def _validate_managed_paths(
    destination: Path, previous: set[str], desired: set[str]
) -> None:
    for relative in previous | set(desired):
        _ensure_no_symlink_parents(destination, relative)
    for relative in set(desired) - previous:
        path = destination / relative
        if path.exists() or path.is_symlink():
            raise ValueError(f"refusing to overwrite an unowned staged file: {path}")


def _write_manifest(path: Path, files: set[str]) -> None:
    path.write_text(
        json.dumps({"managed_files": sorted(files)}, indent=2) + "\n",
        encoding="utf-8",
    )


def _remove_stale_files(destination: Path, stale: set[str]) -> None:
    for relative in sorted(stale, key=lambda item: item.count("/"), reverse=True):
        path = destination / relative
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.exists():
            raise ValueError(f"refusing to remove a non-file staged path: {path}")


def _write_desired_files(destination: Path, desired: dict[str, bytes]) -> None:
    for relative, content in desired.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            path.unlink()
        path.write_bytes(content)


def _remove_empty_parents(destination: Path, stale: set[str]) -> None:
    for relative in stale:
        parent = (destination / relative).parent
        while parent != destination and destination in parent.parents:
            if not _remove_empty_directory(parent):
                break
            parent = parent.parent


def _remove_empty_directory(path: Path) -> bool:
    try:
        path.rmdir()
    except OSError:
        return False
    return True


def stage_application(project_root: Path, target: Path) -> tuple[str, ...]:
    """Copy only App build inputs to a dedicated, script-owned local App folder."""
    project = project_root.resolve(strict=True)
    destination = _resolve_target(project, target)
    desired = _desired_files(project)
    previous = _managed_files(destination)
    _validate_managed_paths(destination, previous, set(desired))

    destination.mkdir(parents=True, exist_ok=True)
    manifest = destination / MANIFEST_NAME
    # Record the union first so an interrupted stage can be safely resumed.
    _write_manifest(manifest, previous | set(desired))
    stale = previous - set(desired)
    _remove_stale_files(destination, stale)
    _write_desired_files(destination, desired)
    _remove_empty_parents(destination, stale)
    _write_manifest(manifest, set(desired))
    return tuple(sorted(desired))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help=f"dedicated local App source directory (default: {DEFAULT_TARGET})",
    )
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    try:
        files = stage_application(project, args.target)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Staged {len(files)} App build files at {args.target.resolve()}")
    print("Local build metadata omits the published image reference by design.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
