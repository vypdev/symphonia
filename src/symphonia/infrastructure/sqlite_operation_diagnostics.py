"""Bounded read-only support views of durable SQLite operations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import sqlite3
from typing import Any

from symphonia.domain.operations import OperationEvent, OperationRecord
from .sqlite_operation_codec import _bounded_keys, _checkpoint_summary, _parse_utc, _require_text, _utc

_MAX_DIAGNOSTIC_OPERATIONS = 100
_MAX_DIAGNOSTIC_EVENTS = 100


def _require_bounded_int(value: Any, *, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{label} must be an integer between 1 and {maximum}")
    return value


class OperationDiagnostics:
    """Read-only queries and redaction over an existing repository connection."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        get_record: Callable[[str], OperationRecord],
        parse_event: Callable[[sqlite3.Row], OperationEvent],
    ) -> None:
        self._connection = connection
        self._get_record = get_record
        self._parse_event = parse_event

    def diagnostic(self, operation_id: str, *, event_limit: int = 100) -> dict[str, Any]:
        """Return a bounded, redacted support view of one operation."""

        _require_text(operation_id, label="operation_id")
        _require_bounded_int(
            event_limit, label="event_limit", maximum=_MAX_DIAGNOSTIC_EVENTS
        )
        record = self._get_record(operation_id)
        event_rows = self._connection.execute(
            """
            SELECT sequence, operation_id, event_type, state, worker_id, payload_json, created_at
              FROM operation_events
             WHERE operation_id = ?
             ORDER BY sequence DESC
             LIMIT ?
            """,
            (operation_id, event_limit + 1),
        ).fetchall()
        events_truncated = len(event_rows) > event_limit
        selected_events = tuple(
            self._parse_event(row) for row in reversed(event_rows[:event_limit])
        )
        payload_keys, payload_keys_truncated = _bounded_keys(record.payload)
        return {
            "operation_id": record.operation_id,
            "operation_type": record.operation_type,
            "state": record.state,
            "worker_id": record.worker_id,
            "next_run_at": None if record.next_run_at is None else _utc(record.next_run_at),
            "cancel_requested": record.cancel_requested,
            "created_at": _utc(record.created_at),
            "updated_at": _utc(record.updated_at),
            "payload_keys": payload_keys,
            "payload_keys_truncated": payload_keys_truncated,
            "checkpoint": _checkpoint_summary(record.checkpoint),
            "events_truncated": events_truncated,
            "events": [
                {
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "state": event.state,
                    "worker_id": event.worker_id,
                    "payload": event.payload,
                    "created_at": _utc(event.created_at),
                }
                for event in selected_events
            ],
        }

    def diagnostics(self, *, limit: int = 50, event_limit: int = 20) -> tuple[dict[str, Any], ...]:
        """Return a bounded list of redacted operation support views."""

        _require_bounded_int(limit, label="limit", maximum=_MAX_DIAGNOSTIC_OPERATIONS)
        _require_bounded_int(
            event_limit, label="event_limit", maximum=_MAX_DIAGNOSTIC_EVENTS
        )
        rows = self._connection.execute(
            """
            SELECT operation_id
              FROM operations
             ORDER BY updated_at DESC, operation_id DESC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return tuple(self.diagnostic(row["operation_id"], event_limit=event_limit) for row in rows)

    def queue_summary(self, *, now: datetime) -> dict[str, Any]:
        """Return aggregate queue health without exposing operation payloads."""

        now_text = _utc(now)
        state_rows = self._connection.execute(
            "SELECT state, COUNT(*) AS count FROM operations GROUP BY state"
        ).fetchall()
        states = {str(row["state"]): int(row["count"]) for row in state_rows}
        eligible = self._connection.execute(
            """
            SELECT COUNT(*) AS count,
                   MIN(
                       CASE WHEN state = 'running'
                            THEN COALESCE(lease_expires_at, created_at)
                            ELSE COALESCE(next_run_at, created_at)
                       END
                   ) AS oldest_eligible_at
              FROM operations
             WHERE cancel_requested = 0
               AND (
                    state = 'queued'
                    OR (state IN ('retry_scheduled', 'waiting_rate_limit')
                        AND next_run_at IS NOT NULL AND next_run_at <= ?)
                    OR (state = 'running'
                        AND (lease_expires_at IS NULL OR lease_expires_at <= ?))
               )
            """,
            (now_text, now_text),
        ).fetchone()
        expired_leases = self._connection.execute(
            """
            SELECT COUNT(*) AS count
              FROM operations
             WHERE state = 'running'
               AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
            """,
            (now_text,),
        ).fetchone()
        cancellation_recovery = self._connection.execute(
            """
            SELECT COUNT(*) AS count
             FROM operations
             WHERE cancel_requested = 1
               AND (
                    state = 'waiting_user'
                    OR (state = 'running'
                        AND (lease_expires_at IS NULL OR lease_expires_at <= ?))
               )
            """,
            (now_text,),
        ).fetchone()
        cancellation_rows = self._connection.execute(
            "SELECT COUNT(*) AS count FROM operations WHERE cancel_requested = 1"
        ).fetchone()
        oldest_eligible_at = eligible["oldest_eligible_at"]
        oldest_eligible_age_seconds = None
        if oldest_eligible_at is not None:
            oldest_eligible_age_seconds = max(
                0,
                int((now - _parse_utc(oldest_eligible_at)).total_seconds()),
            )
        return {
            "total": sum(states.values()),
            "states": states,
            "eligible_count": int(eligible["count"]),
            "expired_lease_count": int(expired_leases["count"]),
            "oldest_eligible_at": oldest_eligible_at,
            "oldest_eligible_age_seconds": oldest_eligible_age_seconds,
            "cancellation_requested_count": int(cancellation_rows["count"]),
            "cancellation_recovery_required_count": int(cancellation_recovery["count"]),
        }
