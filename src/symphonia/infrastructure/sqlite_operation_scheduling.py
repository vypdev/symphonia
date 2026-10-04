"""Atomic retry scheduling and cancellation quarantine for durable operations."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from symphonia.domain.operations import LeaseConflict, OperationRecord

from .sqlite_operation_codec import _checkpoint_summary, _require_text, _utc, _validate_object_payload
from .sqlite_operation_context import OperationContext
from .sqlite_operation_rules import OperationNotFound, _checkpoint_requires_reconciliation
from .sqlite_operation_transactions import _rollback_after_error


def schedule_retry(
    context: OperationContext,
    operation_id: str,
    *,
    worker_id: str,
    next_run_at: datetime,
    checkpoint: dict[str, Any],
    now: datetime,
) -> OperationRecord:
    """Release a lease and persist a restart-safe retry time."""

    return _schedule_wait(
        context, operation_id, worker_id=worker_id, next_run_at=next_run_at,
        checkpoint=checkpoint, now=now, state="retry_scheduled",
        event_type="retry_scheduled",
    )


def schedule_rate_limit(
    context: OperationContext,
    operation_id: str,
    *,
    worker_id: str,
    next_run_at: datetime,
    checkpoint: dict[str, Any],
    now: datetime,
) -> OperationRecord:
    """Release a lease until an absolute provider rate-limit time."""

    return _schedule_wait(
        context, operation_id, worker_id=worker_id, next_run_at=next_run_at,
        checkpoint=checkpoint, now=now, state="waiting_rate_limit",
        event_type="rate_limit_wait",
    )


def _schedule_wait(
    context: OperationContext,
    operation_id: str,
    *,
    worker_id: str,
    next_run_at: datetime,
    checkpoint: dict[str, Any],
    now: datetime,
    state: str,
    event_type: str,
) -> OperationRecord:
    _require_text(operation_id, label="operation_id")
    _require_text(worker_id, label="worker_id")
    _validate_object_payload(checkpoint, label="checkpoint")
    now_text = _utc(now)
    next_run_text = _utc(next_run_at)
    checkpoint_json = json.dumps(
        checkpoint, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
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
            if _checkpoint_requires_reconciliation(checkpoint):
                _quarantine_cancelled_outcome(
                    context,
                    operation_id,
                    checkpoint=checkpoint,
                    recovery_reason="cancelled_during_unknown_outcome",
                    now_text=now_text,
                )
                context.connection.execute("COMMIT")
                return context.get(operation_id)
            context.connection.execute(
                """
                UPDATE operations
                   SET state = 'cancelled', checkpoint_json = ?, next_run_at = NULL,
                       worker_id = NULL, lease_expires_at = NULL,
                       cancel_requested = 0, updated_at = ?
                 WHERE operation_id = ?
                """,
                (checkpoint_json, now_text, operation_id),
            )
            context.append_event(
                operation_id=operation_id,
                event_type="cancelled",
                state="cancelled",
                worker_id=None,
                payload=_checkpoint_summary(checkpoint),
                created_at=now_text,
            )
            context.connection.execute("COMMIT")
            return context.get(operation_id)
        context.connection.execute(
            """
            UPDATE operations
               SET state = ?, checkpoint_json = ?, next_run_at = ?,
                   worker_id = NULL, lease_expires_at = NULL, updated_at = ?
             WHERE operation_id = ?
            """,
            (state, checkpoint_json, next_run_text, now_text, operation_id),
        )
        context.append_event(
            operation_id=operation_id,
            event_type=event_type,
            state=state,
            worker_id=None,
            payload={"next_run_at": next_run_text, **_checkpoint_summary(checkpoint)},
            created_at=now_text,
        )
        context.connection.execute("COMMIT")
    except BaseException as error:
        _rollback_after_error(context.connection, error)
        raise
    return context.get(operation_id)


def _quarantine_cancelled_outcome(
    context: OperationContext,
    operation_id: str,
    *,
    checkpoint: dict[str, Any],
    recovery_reason: str,
    now_text: str,
) -> None:
    """Persist reconciliation quarantine inside the caller's transaction."""

    checkpoint = {
        **checkpoint,
        "reconciliation_required": True,
        "recovery_reason": recovery_reason,
    }
    _validate_object_payload(checkpoint, label="operation checkpoint")
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
           SET state = 'waiting_user', checkpoint_json = ?, next_run_at = NULL,
               worker_id = NULL, lease_expires_at = NULL, updated_at = ?
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
            "recovery_reason": recovery_reason,
            **_checkpoint_summary(checkpoint),
        },
        created_at=now_text,
    )
