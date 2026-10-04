"""Shared SQLite operation timestamp and safe audit-summary codecs."""

from __future__ import annotations

from datetime import datetime, timezone
import heapq
from typing import Any

_MAX_DIAGNOSTIC_KEYS = 100


def _require_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _checkpoint_summary(checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Keep audit data useful while excluding checkpoint values by default."""

    checkpoint_keys, checkpoint_keys_truncated = _bounded_keys(checkpoint)
    summary: dict[str, Any] = {
        "checkpoint_keys": checkpoint_keys,
        "checkpoint_keys_truncated": checkpoint_keys_truncated,
        "unknown_step_present": checkpoint.get("unknown_step") is not None,
    }
    reconciliation_required = checkpoint.get("reconciliation_required")
    if isinstance(reconciliation_required, bool):
        summary["reconciliation_required"] = reconciliation_required
    recovery_reason = checkpoint.get("recovery_reason")
    if isinstance(recovery_reason, str) and recovery_reason in {
        "cancelled_worker_lease_expired",
        "cancelled_during_unknown_outcome",
        "cancelled_while_unknown_outcome",
    }:
        summary["recovery_reason"] = recovery_reason
    cancellation_resolution = checkpoint.get("cancellation_resolution")
    if isinstance(cancellation_resolution, str) and cancellation_resolution in {
        "no_effect",
        "effect_confirmed",
    }:
        summary["cancellation_resolution"] = cancellation_resolution
    for key in ("confirmed_occurrences", "issues"):
        value = checkpoint.get(key)
        if isinstance(value, (list, tuple, set)):
            summary[f"{key}_count"] = len(value)
    return summary


def _bounded_keys(value: dict[str, Any]) -> tuple[list[str], bool]:
    keys = heapq.nsmallest(_MAX_DIAGNOSTIC_KEYS + 1, (str(key) for key in value))
    return keys[:_MAX_DIAGNOSTIC_KEYS], len(keys) > _MAX_DIAGNOSTIC_KEYS
