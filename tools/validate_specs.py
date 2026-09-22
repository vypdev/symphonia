"""Validate the repository-native SDD/catalog consistency rules.

This intentionally uses only the Python standard library.  It checks the
manual rules documented in ``specs/README.md`` so a future implementation can
rely on the same checks locally and in CI without selecting an application
toolchain first.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


CAPABILITY_ID_RE = re.compile(r"^\s*-\s+Catalog capability ID:\s+`([^`]+)`\s*$", re.MULTILINE)
REQUIREMENT_RE = re.compile(r"\bSYM-[A-Z]+-[0-9]{3}\b")
CATALOG_ROW_RE = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*\[[^]]+\]\(([^)]+)\)\s*\|",
    re.MULTILINE,
)
MARKDOWN_LINK_RE = re.compile(r"(?<!!)(?:\[[^]]+\])\((?:<([^>]+)>|([^\s)]+))(?:\s+[^)]*)?\)")

CATALOG_STATUSES = {
    "draft": "Draft",
    "ready-for-review": "Ready for review",
    "ready-for-implementation": "Ready for implementation",
    "implemented": "Implemented",
    "superseded": "Superseded",
}
EXCLUDED_SPEC_MARKDOWN = {"README.md", "CATALOG.md", "_template.md"}


def _add(errors: list[str], message: str) -> None:
    errors.append(message)


def _local_path(root: Path, raw: str) -> Path:
    return root / raw


def _validate_catalog_shape(root: Path, catalog: Any, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(catalog, dict):
        _add(errors, "catalog.json must contain an object")
        return []
    if catalog.get("version") != 1:
        _add(errors, "catalog.json version must be 1")
    capabilities = catalog.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        _add(errors, "catalog.json capabilities must be a non-empty array")
        return []

    ids: set[str] = set()
    specifications: set[str] = set()
    for index, capability in enumerate(capabilities):
        prefix = f"catalog capability {index}"
        if not isinstance(capability, dict):
            _add(errors, f"{prefix} must be an object")
            continue
        for field in (
            "id",
            "title",
            "status",
            "scope",
            "owner",
            "specification",
            "requirements",
            "evidence",
            "implementationEvidence",
            "blockers",
        ):
            if field not in capability:
                _add(errors, f"{prefix} is missing {field!r}")
        capability_id = capability.get("id")
        if not isinstance(capability_id, str) or not capability_id:
            _add(errors, f"{prefix} has an invalid id")
        elif capability_id in ids:
            _add(errors, f"duplicate catalog capability id: {capability_id}")
        else:
            ids.add(capability_id)
        status = capability.get("status")
        if status not in CATALOG_STATUSES:
            _add(errors, f"{prefix} has invalid status: {status!r}")
        specification = capability.get("specification")
        if not isinstance(specification, str) or not specification:
            _add(errors, f"{prefix} has an invalid specification path")
        elif specification in specifications:
            _add(errors, f"multiple capabilities use primary SDD: {specification}")
        else:
            specifications.add(specification)
        requirements = capability.get("requirements")
        if not isinstance(requirements, list) or len(requirements) != len(set(requirements)):
            _add(errors, f"{prefix} requirements must be a unique array")

        for field in ("evidence", "blockers"):
            if not isinstance(capability.get(field), list):
                _add(errors, f"{prefix} {field} must be an array")
        implementation = capability.get("implementationEvidence")
        if not isinstance(implementation, dict):
            _add(errors, f"{prefix} implementationEvidence must be an object")
        else:
            for field in ("code", "tests", "documentation"):
                if not isinstance(implementation.get(field), list):
                    _add(errors, f"{prefix} implementationEvidence.{field} must be an array")
    return [capability for capability in capabilities if isinstance(capability, dict)]


def _validate_paths(root: Path, capabilities: list[dict[str, Any]], errors: list[str]) -> None:
    for capability in capabilities:
        capability_id = capability.get("id", "<unknown>")
        paths: list[str] = []
        for field in ("specification", "evidence"):
            values = capability.get(field, [])
            paths.extend([values] if isinstance(values, str) else values if isinstance(values, list) else [])
        implementation = capability.get("implementationEvidence", {})
        if isinstance(implementation, dict):
            for values in implementation.values():
                if isinstance(values, list):
                    paths.extend(values)
        for raw_path in paths:
            if not isinstance(raw_path, str):
                _add(errors, f"{capability_id} contains a non-string path")
                continue
            path = _local_path(root, raw_path)
            if not path.exists():
                _add(errors, f"{capability_id} references missing path: {raw_path}")


def _validate_sdds(root: Path, capabilities: list[dict[str, Any]], errors: list[str]) -> None:
    by_id = {capability.get("id"): capability for capability in capabilities}
    for capability in capabilities:
        capability_id = capability.get("id")
        specification = capability.get("specification")
        if not isinstance(capability_id, str) or not isinstance(specification, str):
            continue
        path = _local_path(root, specification)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        matches = CAPABILITY_ID_RE.findall(text)
        if matches != [capability_id]:
            _add(errors, f"{specification} must declare exactly catalog capability ID {capability_id!r}")
        status_match = re.search(r"^\s*-\s+Status:\s+(.+?)\s*$", text, re.MULTILINE)
        expected_status = CATALOG_STATUSES.get(capability.get("status"))
        if status_match and expected_status and status_match.group(1) != expected_status:
            _add(errors, f"{specification} status {status_match.group(1)!r} disagrees with catalog {expected_status!r}")

    for path in sorted((root / "specs").glob("*.md")):
        if path.name in EXCLUDED_SPEC_MARKDOWN:
            continue
        text = path.read_text(encoding="utf-8")
        matches = CAPABILITY_ID_RE.findall(text)
        if len(matches) != 1:
            _add(errors, f"{path.relative_to(root)} must declare exactly one catalog capability ID")
        elif matches[0] not in by_id:
            _add(errors, f"{path.relative_to(root)} uses unknown catalog capability ID {matches[0]!r}")


def _validate_requirements(root: Path, capabilities: list[dict[str, Any]], errors: list[str]) -> None:
    known: set[str] = set()
    for path in (root / "docs").rglob("*.md"):
        known.update(REQUIREMENT_RE.findall(path.read_text(encoding="utf-8")))
    for capability in capabilities:
        for requirement in capability.get("requirements", []):
            if requirement not in known:
                _add(errors, f"{capability.get('id', '<unknown>')} references unknown requirement {requirement}")


def _validate_catalog_markdown(root: Path, capabilities: list[dict[str, Any]], errors: list[str]) -> None:
    path = root / "specs" / "CATALOG.md"
    if not path.is_file():
        _add(errors, "specs/CATALOG.md is missing")
        return
    rows = {match.group(1): (match.group(2).strip(), match.group(3)) for match in CATALOG_ROW_RE.finditer(path.read_text(encoding="utf-8"))}
    expected = {capability.get("id"): capability for capability in capabilities}
    if set(rows) != set(expected):
        _add(errors, "specs/CATALOG.md capability rows disagree with catalog.json")
    for capability_id, capability in expected.items():
        row = rows.get(capability_id)
        if row is None:
            continue
        expected_status = CATALOG_STATUSES.get(capability.get("status"))
        expected_path = Path(capability.get("specification", "")).name
        if row != (expected_status, expected_path):
            _add(errors, f"specs/CATALOG.md row for {capability_id} disagrees with catalog.json")


def _validate_markdown_links(root: Path, errors: list[str]) -> None:
    for path in sorted(root.rglob("*.md")):
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK_RE.finditer(text):
            target = match.group(1) or match.group(2)
            if not target or target.startswith(("http://", "https://", "mailto:", "#", "codex://")):
                continue
            target_path = target.split("#", 1)[0].split("?", 1)[0]
            if not target_path:
                continue
            candidate = (path.parent / target_path).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                _add(errors, f"{path.relative_to(root)} links outside repository: {target}")
                continue
            if not candidate.exists():
                _add(errors, f"{path.relative_to(root)} links to missing path: {target}")


def validate(root: Path) -> list[str]:
    """Return all catalog/SDD consistency errors for ``root``."""

    errors: list[str] = []
    catalog_path = root / "specs" / "catalog.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["specs/catalog.json is missing"]
    except json.JSONDecodeError as error:
        return [f"specs/catalog.json is invalid JSON: {error}"]
    capabilities = _validate_catalog_shape(root, catalog, errors)
    _validate_paths(root, capabilities, errors)
    _validate_sdds(root, capabilities, errors)
    _validate_requirements(root, capabilities, errors)
    _validate_catalog_markdown(root, capabilities, errors)
    _validate_markdown_links(root, errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Symphonia SDD/catalog consistency")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    errors = validate(args.root.resolve())
    if errors:
        print(f"spec validation failed with {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("spec validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
