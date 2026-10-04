"""Allowlisted, read-only view model for the administrator dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _count(value: object) -> int:
    return value if type(value) is int and 0 <= value <= 1_000_000_000 else 0


def _label(value: object, *, limit: int = 80) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value[:limit] if character.isprintable())


def _counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, count in list(value.items())[:30]:
        label = _label(key, limit=40)
        if label:
            result[label] = _count(count)
    return result


def _date(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat()


def project_dashboard(diagnostics: dict[str, Any], *, now: datetime, version: str) -> dict[str, Any]:
    """Only expose aggregate facts and a small operation identity/state list."""
    if diagnostics.get("ready") is not True:
        return {"service": "symphonia", "ready": False}

    queue = diagnostics.get("queue") or {}
    connections = diagnostics.get("connections") or {}
    projections = diagnostics.get("projections") or {}
    resolutions = diagnostics.get("resolutions") or {}
    operations = diagnostics.get("operations") or ()

    provider_counts = connections.get("by_provider") or {}
    by_provider = {
        _label(provider, limit=40): _counts(states)
        for provider, states in list(provider_counts.items())[:10]
        if _label(provider, limit=40)
    } if isinstance(provider_counts, dict) else {}

    recent = []
    if isinstance(operations, (list, tuple)):
        for operation in operations[:10]:
            if not isinstance(operation, dict):
                continue
            recent.append({
                "id": _label(operation.get("operation_id"), limit=64),
                "type": _label(operation.get("operation_type"), limit=40),
                "state": _label(operation.get("state"), limit=40),
                "updated_at": _date(operation.get("updated_at")),
            })

    return {
        "service": "symphonia",
        "version": _label(version, limit=32),
        "ready": True,
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "queue": {
            "total": _count(queue.get("total")),
            "eligible_count": _count(queue.get("eligible_count")),
            "states": _counts(queue.get("states")),
        },
        "connections": {
            "total": _count(connections.get("total")),
            "expired_count": _count(connections.get("expired_count")),
            "by_provider": by_provider,
        },
        "library": {
            "current_playlists": _count(projections.get("current_playlist_count")),
            "entries": _count(projections.get("entry_count")),
            "unavailable_entries": _count(projections.get("unavailable_entry_count")),
            "latest_published_at": _date(projections.get("latest_published_at")),
        },
        "resolutions": {
            "total": _count(resolutions.get("total")),
            "by_action": _counts(resolutions.get("by_action")),
        },
        "operations": recent,
    }
