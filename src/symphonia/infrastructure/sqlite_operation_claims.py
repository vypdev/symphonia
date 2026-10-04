"""Atomic lease claims, recovery selection, and renewal on one SQLite connection."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import Any

from symphonia.domain.operations import LeaseConflict, OperationRecord

from .sqlite_operation_codec import _checkpoint_summary, _load_json_object, _require_text, _utc
from .sqlite_operation_context import OperationContext
from .sqlite_operation_rules import OperationNotFound, _require_positive_int
from .sqlite_operation_transactions import _rollback_after_error


def claim(
    context: OperationContext,
    operation_id: str,
    *,
    worker_id: str,
    now: datetime,
    lease_seconds: int = 30,
) -> OperationRecord:
    """Claim queued/retryable work or reclaim a lease that has expired."""

    _require_text(operation_id, label="operation_id")
    _require_text(worker_id, label="worker_id")
    _require_positive_int(lease_seconds, label="lease_seconds")
    now_text = _utc(now)
    expires_text = _utc(now + timedelta(seconds=lease_seconds))
    try:
        context.connection.execute("BEGIN IMMEDIATE")
        row = context.connection.execute(
            "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        if row is None:
            raise OperationNotFound(operation_id)
        if row["cancel_requested"]:
            raise LeaseConflict("operation cancellation has been requested")
        eligible = row["state"] == "queued" or (
            row["state"] in {"retry_scheduled", "waiting_rate_limit"}
            and row["next_run_at"] is not None
            and row["next_run_at"] <= now_text
        )
        expired = row["state"] == "running" and (
            row["lease_expires_at"] is None or row["lease_expires_at"] <= now_text
        )
        if not eligible and not expired:
            raise LeaseConflict(f"operation {operation_id} is not eligible for claim")
        event_type = "lease_reclaimed" if expired else "claimed"
        event_payload = {"lease_expires_at": expires_text}
        if expired and row["worker_id"]:
            event_payload["previous_worker_id"] = row["worker_id"]
        context.connection.execute(
            """
            UPDATE operations
               SET state = 'running', worker_id = ?, lease_expires_at = ?,
                   next_run_at = NULL, updated_at = ?
             WHERE operation_id = ?
            """,
            (worker_id, expires_text, now_text, operation_id),
        )
        context.append_event(
            operation_id=operation_id,
            event_type=event_type,
            state="running",
            worker_id=worker_id,
            payload=event_payload,
            created_at=now_text,
        )
        context.connection.execute("COMMIT")
    except BaseException as error:
        _rollback_after_error(context.connection, error)
        raise
    return context.get(operation_id)


def claim_next(
    context: OperationContext,
    *,
    worker_id: str,
    now: datetime,
    lease_seconds: int = 30,
    operation_type: str | None = None,
) -> OperationRecord | None:
    """Quarantine expired cancelled work, then claim one eligible operation.

    Cancellation recovery never dispatches an ordinary handler. The
    scheduler-facing claim still selects only durable eligibility; handler
    dispatch remains an application concern.
    """

    _require_text(worker_id, label="worker_id")
    if operation_type is not None:
        _require_text(operation_type, label="operation_type")
    _require_positive_int(lease_seconds, label="lease_seconds")
    now_text = _utc(now)
    expires_text = _utc(now + timedelta(seconds=lease_seconds))
    type_clause = " AND operation_type = ?" if operation_type is not None else ""
    parameters: tuple[Any, ...] = (now_text, now_text)
    if operation_type is not None:
        parameters += (operation_type,)
    try:
        context.connection.execute("BEGIN IMMEDIATE")
        # A cancelled worker may have disappeared during an external
        # request. Quarantine one expired lease for explicit resolution;
        # never send it through the ordinary operation handler again.
        uncertain = context.connection.execute(
            """
            SELECT operation_id, checkpoint_json
              FROM operations
             WHERE cancel_requested = 1
               AND state = 'running'
               AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
             ORDER BY COALESCE(lease_expires_at, created_at), created_at, operation_id
             LIMIT 1
            """,
            (now_text,),
        ).fetchone()
        if uncertain is not None:
            operation_id = uncertain["operation_id"]
            checkpoint = _load_json_object(
                uncertain["checkpoint_json"], label="operation checkpoint"
            )
            checkpoint.update(
                {
                    "reconciliation_required": True,
                    "recovery_reason": "cancelled_worker_lease_expired",
                }
            )
            checkpoint_json = json.dumps(
                checkpoint,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            context.connection.execute(
                """
                UPDATE operations
                   SET state = 'waiting_user', checkpoint_json = ?,
                       worker_id = NULL, lease_expires_at = NULL,
                       next_run_at = NULL, updated_at = ?
                 WHERE operation_id = ?
                """,
                (checkpoint_json, now_text, operation_id),
            )
            context.append_event(
                operation_id=operation_id,
                event_type="cancellation_reconciliation_required",
                state="waiting_user",
                worker_id=None,
                payload={
                    "recovery_reason": "cancelled_worker_lease_expired",
                    **_checkpoint_summary(checkpoint),
                },
                created_at=now_text,
            )
        row = context.connection.execute(
            f"""
            SELECT *
              FROM operations
             WHERE cancel_requested = 0
               AND (
                    state = 'queued'
                    OR (state IN ('retry_scheduled', 'waiting_rate_limit')
                        AND next_run_at IS NOT NULL AND next_run_at <= ?)
                    OR (state = 'running' AND (lease_expires_at IS NULL OR lease_expires_at <= ?))
               )
               {type_clause}
             ORDER BY
               CASE WHEN state = 'running' THEN COALESCE(lease_expires_at, created_at)
                    ELSE COALESCE(next_run_at, created_at)
               END ASC,
               created_at ASC,
               operation_id ASC
             LIMIT 1
            """,
            parameters,
        ).fetchone()
        if row is None:
            context.connection.execute("COMMIT")
            return None
        operation_id = row["operation_id"]
        recovered = row["state"] == "running"
        event_type = "lease_reclaimed" if recovered else "claimed"
        event_payload = {"lease_expires_at": expires_text}
        if recovered and row["worker_id"]:
            event_payload["previous_worker_id"] = row["worker_id"]
        context.connection.execute(
            """
            UPDATE operations
               SET state = 'running', worker_id = ?, lease_expires_at = ?,
                   next_run_at = NULL, updated_at = ?
             WHERE operation_id = ?
            """,
            (worker_id, expires_text, now_text, operation_id),
        )
        context.append_event(
            operation_id=operation_id,
            event_type=event_type,
            state="running",
            worker_id=worker_id,
            payload=event_payload,
            created_at=now_text,
        )
        context.connection.execute("COMMIT")
    except BaseException as error:
        _rollback_after_error(context.connection, error)
        raise
    return context.get(operation_id)


def renew_lease(
    context: OperationContext,
    operation_id: str,
    *,
    worker_id: str,
    now: datetime,
    lease_seconds: int = 30,
) -> OperationRecord:
    """Extend a healthy, non-cancelled lease; stale owners cannot revive it."""

    _require_text(operation_id, label="operation_id")
    _require_text(worker_id, label="worker_id")
    _require_positive_int(lease_seconds, label="lease_seconds")
    now_text = _utc(now)
    expires_text = _utc(now + timedelta(seconds=lease_seconds))
    try:
        context.connection.execute("BEGIN IMMEDIATE")
        row = context.connection.execute(
            "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        if row is None:
            raise OperationNotFound(operation_id)
        if row["state"] != "running" or row["worker_id"] != worker_id:
            raise LeaseConflict("worker does not own a running operation")
        if row["cancel_requested"]:
            raise LeaseConflict("operation cancellation has been requested")
        if row["lease_expires_at"] is not None and row["lease_expires_at"] <= now_text:
            raise LeaseConflict("operation lease has expired")
        context.connection.execute(
            "UPDATE operations SET lease_expires_at = ?, updated_at = ? WHERE operation_id = ?",
            (expires_text, now_text, operation_id),
        )
        context.append_event(
            operation_id=operation_id,
            event_type="lease_renewed",
            state="running",
            worker_id=worker_id,
            payload={"lease_expires_at": expires_text},
            created_at=now_text,
        )
        context.connection.execute("COMMIT")
    except BaseException as error:
        _rollback_after_error(context.connection, error)
        raise
    return context.get(operation_id)
