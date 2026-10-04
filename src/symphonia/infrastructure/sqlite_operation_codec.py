"""Shared SQLite operation timestamp and safe audit-summary codecs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import heapq
import json
import re
import sqlite3
from typing import Any

from symphonia.domain.operations import OperationEvent, OperationRecord

_SECRET_PAYLOAD_KEY = re.compile(
    r"(?i)(?:^|[_-])(access[_-]?token|refresh[_-]?token|id[_-]?token|client[_-]?secret|api[_-]?key|password|cookie|authorization|secret[_-]?token)(?:$|[_-])|^(?:secret|token)$"
)
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_OPERATION_STATES = frozenset(
    {
        "queued",
        "running",
        "waiting_rate_limit",
        "waiting_user",
        "retry_scheduled",
        "succeeded",
        "partial",
        "failed",
        "cancelled",
    }
)


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


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-standard JSON constant is not allowed: {value}")


def _load_json(value: str) -> Any:
    return json.loads(value, parse_constant=_reject_non_finite_json)


def _load_json_object(value: str, *, label: str) -> dict[str, Any]:
    parsed = _load_json(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    return parsed


def _validate_payload_keys(payload: Any, *, label: str = "operation payload") -> None:
    forbidden_key_found = False
    active_containers: set[int] = set()

    def walk(value: Any) -> None:
        nonlocal forbidden_key_found
        if isinstance(value, Mapping):
            identity = id(value)
            if identity in active_containers:
                raise ValueError(f"{label} must not contain cyclic structures")
            active_containers.add(identity)
            try:
                for key, nested in value.items():
                    if not isinstance(key, str):
                        raise ValueError(f"{label} object keys must be strings")
                    key_text = str(key)
                    normalized_key = _CAMEL_CASE_BOUNDARY.sub("_", key_text)
                    if _SECRET_PAYLOAD_KEY.search(normalized_key):
                        forbidden_key_found = True
                    walk(nested)
            finally:
                active_containers.remove(identity)
            return
        if isinstance(value, (list, tuple)):
            identity = id(value)
            if identity in active_containers:
                raise ValueError(f"{label} must not contain cyclic structures")
            active_containers.add(identity)
            try:
                for nested in value:
                    walk(nested)
            finally:
                active_containers.remove(identity)

    walk(payload)
    if forbidden_key_found:
        raise ValueError(f"{label} contains credential-shaped keys")


def _validate_object_payload(payload: Any, *, label: str) -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    _validate_payload_keys(payload, label=label)


def _record(row: sqlite3.Row) -> OperationRecord:
    state = row["state"]
    if state not in _OPERATION_STATES:
        raise ValueError(f"operation store contains invalid state: {state!r}")
    if row["cancel_requested"] not in (0, 1):
        raise ValueError("operation store contains an invalid cancellation flag")
    payload = _load_json_object(row["payload_json"], label="operation payload")
    checkpoint = _load_json_object(row["checkpoint_json"], label="operation checkpoint")
    _validate_payload_keys(payload, label="operation payload")
    _validate_payload_keys(checkpoint, label="operation checkpoint")
    return OperationRecord(
        operation_id=row["operation_id"],
        operation_type=row["operation_type"],
        state=state,
        idempotency_key=row["idempotency_key"],
        payload=payload,
        checkpoint=checkpoint,
        worker_id=row["worker_id"],
        lease_expires_at=None if row["lease_expires_at"] is None else _parse_utc(row["lease_expires_at"]),
        next_run_at=None if row["next_run_at"] is None else _parse_utc(row["next_run_at"]),
        cancel_requested=bool(row["cancel_requested"]),
        created_at=_parse_utc(row["created_at"]),
        updated_at=_parse_utc(row["updated_at"]),
    )

def _event(row: sqlite3.Row) -> OperationEvent:
    state = row["state"]
    if state not in _OPERATION_STATES:
        raise ValueError(f"operation event contains invalid state: {state!r}")
    payload = _load_json_object(row["payload_json"], label="operation event payload")
    _validate_payload_keys(payload, label="operation event payload")
    return OperationEvent(
        sequence=row["sequence"],
        operation_id=row["operation_id"],
        event_type=row["event_type"],
        state=state,
        worker_id=row["worker_id"],
        payload=payload,
        created_at=_parse_utc(row["created_at"]),
    )
