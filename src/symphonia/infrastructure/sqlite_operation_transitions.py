"""Atomic operation checkpoints and user-driven state transitions."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from symphonia.domain.operations import LeaseConflict, OperationRecord

from .sqlite_operation_codec import (
    _checkpoint_summary, _load_json_object, _require_text, _utc, _validate_object_payload,
)
from .sqlite_operation_context import OperationContext
from .sqlite_operation_rules import OperationNotFound, _checkpoint_requires_reconciliation
from .sqlite_operation_transactions import _rollback_after_error


def checkpoint(
    context: OperationContext,
    operation_id: str,
    *,
    worker_id: str,
    checkpoint: dict[str, Any],
    now: datetime,
    state: str = "running",
) -> OperationRecord:
    """Persist a checkpoint only for the current, unexpired lease holder."""

    _require_text(operation_id, label="operation_id")
    _require_text(worker_id, label="worker_id")
    if not isinstance(state, str) or state not in {
        "running",
        "succeeded",
        "partial",
        "failed",
        "cancelled",
        "waiting_user",
    }:
        raise ValueError("invalid checkpoint state")
    _validate_object_payload(checkpoint, label="checkpoint")
    now_text = _utc(now)
    try:
        context.connection.execute("BEGIN IMMEDIATE")
        row = context.connection.execute(
            "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        if row is None:
            raise OperationNotFound(operation_id)
        if row["state"] != "running" or row["worker_id"] != worker_id:
            raise LeaseConflict("worker does not own a running operation")
        if row["lease_expires_at"] is not None and row["lease_expires_at"] <= now_text:
            raise LeaseConflict("operation lease has expired")
        effective_state = state
        if row["cancel_requested"] and state in {"running", "cancelled", "waiting_user"}:
            if _checkpoint_requires_reconciliation(checkpoint):
                effective_state = "waiting_user"
                checkpoint = {
                    **checkpoint,
                    "reconciliation_required": True,
                    "recovery_reason": "cancelled_during_unknown_outcome",
                }
            else:
                effective_state = "cancelled"
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
               SET state = ?, checkpoint_json = ?, updated_at = ?,
                   worker_id = CASE WHEN ? = 'running' THEN worker_id ELSE NULL END,
                   lease_expires_at = CASE WHEN ? = 'running' THEN lease_expires_at ELSE NULL END,
                   cancel_requested = CASE
                       WHEN ? IN ('cancelled', 'succeeded', 'partial', 'failed') THEN 0
                       ELSE cancel_requested
                   END
             WHERE operation_id = ?
            """,
            (
                effective_state,
                checkpoint_json,
                now_text,
                effective_state,
                effective_state,
                effective_state,
                operation_id,
            ),
        )
        context.append_event(
            operation_id=operation_id,
            event_type="checkpointed",
            state=effective_state,
            worker_id=worker_id if effective_state == "running" else None,
            payload=_checkpoint_summary(checkpoint),
            created_at=now_text,
        )
        context.connection.execute("COMMIT")
    except BaseException as error:
        _rollback_after_error(context.connection, error)
        raise
    return context.get(operation_id)


def cancel(context: OperationContext, operation_id: str, *, now: datetime) -> OperationRecord:
    """Request cooperative cancellation and preserve in-flight ownership."""

    _require_text(operation_id, label="operation_id")
    now_text = _utc(now)
    try:
        context.connection.execute("BEGIN IMMEDIATE")
        row = context.connection.execute(
            "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        if row is None:
            raise OperationNotFound(operation_id)
        if row["state"] in {"succeeded", "partial", "failed", "cancelled"}:
            context.connection.execute("COMMIT")
            return context.get(operation_id)
        if row["state"] == "waiting_user" and row["cancel_requested"]:
            # Repeated cancellation is not a resolution of an unknown
            # provider outcome. Preserve the actionable quarantine.
            context.connection.execute("COMMIT")
            return context.get(operation_id)
        if row["state"] == "waiting_user":
            checkpoint = _load_json_object(
                row["checkpoint_json"], label="operation checkpoint"
            )
            if _checkpoint_requires_reconciliation(checkpoint):
                checkpoint.update(
                    {
                        "reconciliation_required": True,
                        "recovery_reason": "cancelled_while_unknown_outcome",
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
                       SET checkpoint_json = ?, cancel_requested = 1, updated_at = ?
                     WHERE operation_id = ?
                    """,
                    (checkpoint_json, now_text, operation_id),
                )
                context.append_event(
                    operation_id=operation_id,
                    event_type="cancellation_requested",
                    state="waiting_user",
                    worker_id=None,
                    payload={"recovery_reason": "cancelled_while_unknown_outcome"},
                    created_at=now_text,
                )
                context.connection.execute("COMMIT")
                return context.get(operation_id)
        if row["state"] == "running":
            context.connection.execute(
                "UPDATE operations SET cancel_requested = 1, updated_at = ? WHERE operation_id = ?",
                (now_text, operation_id),
            )
            context.append_event(
                operation_id=operation_id,
                event_type="cancellation_requested",
                state="running",
                worker_id=row["worker_id"],
                payload={},
                created_at=now_text,
            )
        else:
            context.connection.execute(
                """
                UPDATE operations
                   SET state = 'cancelled', worker_id = NULL, lease_expires_at = NULL,
                       cancel_requested = 0, updated_at = ?
                 WHERE operation_id = ?
                """,
                (now_text, operation_id),
            )
            context.append_event(
                operation_id=operation_id,
                event_type="cancelled",
                state="cancelled",
                worker_id=None,
                payload={},
                created_at=now_text,
            )
        context.connection.execute("COMMIT")
    except BaseException as error:
        _rollback_after_error(context.connection, error)
        raise
    return context.get(operation_id)


def resume(context: OperationContext, operation_id: str, *, now: datetime) -> OperationRecord:
    """Re-admit a user-action operation after its external issue is resolved."""

    _require_text(operation_id, label="operation_id")
    now_text = _utc(now)
    try:
        context.connection.execute("BEGIN IMMEDIATE")
        row = context.connection.execute(
            "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        if row is None:
            raise OperationNotFound(operation_id)
        if row["state"] != "waiting_user":
            raise LeaseConflict("only waiting_user operations can be resumed")
        checkpoint = _load_json_object(
            row["checkpoint_json"], label="operation checkpoint"
        )
        if (
            row["cancel_requested"]
            or checkpoint.get("reconciliation_required") is True
        ):
            raise LeaseConflict(
                "cancellation recovery must be resolved before operation can resume"
            )
        context.connection.execute(
            "UPDATE operations SET state = 'queued', updated_at = ? WHERE operation_id = ?",
            (now_text, operation_id),
        )
        context.append_event(
            operation_id=operation_id,
            event_type="resumed",
            state="queued",
            worker_id=None,
            payload={},
            created_at=now_text,
        )
        context.connection.execute("COMMIT")
    except BaseException as error:
        _rollback_after_error(context.connection, error)
        raise
    return context.get(operation_id)


def resolve_cancelled_outcome(
    context: OperationContext,
    operation_id: str,
    *,
    outcome: str,
    now: datetime,
) -> OperationRecord:
    """Persist an explicit manual resolution of an uncertain cancelled write.

    Callers must authorize the human/operator action before invoking this
    repository primitive. An unresolved outcome stays in ``waiting_user``
    and cannot be resumed through the ordinary operation path.
    """

    _require_text(operation_id, label="operation_id")
    if not isinstance(outcome, str) or outcome not in {"no_effect", "effect_confirmed"}:
        raise ValueError("outcome must be 'no_effect' or 'effect_confirmed'")
    now_text = _utc(now)
    try:
        context.connection.execute("BEGIN IMMEDIATE")
        row = context.connection.execute(
            "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        if row is None:
            raise OperationNotFound(operation_id)
        if row["state"] != "waiting_user" or not row["cancel_requested"]:
            raise LeaseConflict("operation has no unresolved cancellation outcome")
        checkpoint = _load_json_object(
            row["checkpoint_json"], label="operation checkpoint"
        )
        if checkpoint.get("reconciliation_required") is not True:
            raise LeaseConflict("operation is not awaiting cancellation reconciliation")
        checkpoint["cancellation_resolution"] = outcome
        checkpoint_json = json.dumps(
            checkpoint,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        resolved_state = "cancelled" if outcome == "no_effect" else "partial"
        context.connection.execute(
            """
            UPDATE operations
               SET state = ?, checkpoint_json = ?, cancel_requested = 0,
                   worker_id = NULL, lease_expires_at = NULL,
                   next_run_at = NULL, updated_at = ?
             WHERE operation_id = ?
            """,
            (resolved_state, checkpoint_json, now_text, operation_id),
        )
        context.append_event(
            operation_id=operation_id,
            event_type="cancellation_reconciled",
            state=resolved_state,
            worker_id=None,
            payload={"outcome": outcome},
            created_at=now_text,
        )
        context.connection.execute("COMMIT")
    except BaseException as error:
        _rollback_after_error(context.connection, error)
        raise
    return context.get(operation_id)
