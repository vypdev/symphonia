"""Transactional SQLite state machine for durable operations and worker leases."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from functools import wraps
import json
import re
import sqlite3
from threading import RLock
from typing import Any, Concatenate, ParamSpec, TypeVar
import uuid

from symphonia.domain.operations import LeaseConflict, OperationEvent, OperationRecord

from .sqlite_common import connect, initialize_with_cleanup
from .sqlite_operation_codec import _checkpoint_summary, _parse_utc, _require_text, _utc
from .sqlite_operation_diagnostics import OperationDiagnostics


class OperationNotFound(LookupError):
    pass


class IdempotencyConflict(ValueError):
    pass


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


def _require_positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-standard JSON constant is not allowed: {value}")


def _load_json(value: str) -> Any:
    return json.loads(value, parse_constant=_reject_non_finite_json)


def _load_json_object(value: str, *, label: str) -> dict[str, Any]:
    parsed = _load_json(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    return parsed


def _rollback_after_error(connection: sqlite3.Connection, error: BaseException) -> None:
    """Release an interrupted transaction without hiding its primary failure."""

    if not connection.in_transaction:
        return
    try:
        connection.execute("ROLLBACK")
    except BaseException as rollback_error:
        error.add_note(
            "SQLite transaction rollback also failed "
            f"({type(rollback_error).__name__})"
        )


_RepositoryArgs = ParamSpec("_RepositoryArgs")
_RepositoryResult = TypeVar("_RepositoryResult")


def _serialize_repository_access(
    method: Callable[Concatenate[Any, _RepositoryArgs], _RepositoryResult],
) -> Callable[Concatenate[Any, _RepositoryArgs], _RepositoryResult]:
    """Keep each use of a shared SQLite connection within one local critical section."""

    @wraps(method)
    def wrapped(
        self: Any,
        *args: _RepositoryArgs.args,
        **kwargs: _RepositoryArgs.kwargs,
    ) -> _RepositoryResult:
        with self._connection_lock:
            return method(self, *args, **kwargs)

    return wrapped


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


def _checkpoint_requires_reconciliation(checkpoint: dict[str, Any]) -> bool:
    return (
        checkpoint.get("unknown_step") is not None
        or checkpoint.get("reconciliation_required") is True
    )


class OperationRepository:
    """Transactional operation repository backed by one SQLite database."""

    SCHEMA_VERSION = 3

    def __init__(self, path: str = ":memory:") -> None:
        self._connection_lock = RLock()
        self._connection = connect(path)
        initialize_with_cleanup(self._connection, self._migrate)
        self._diagnostic_views = OperationDiagnostics(self._connection, self.get, self._event)

    @_serialize_repository_access
    def close(self) -> None:
        self._connection.close()

    @_serialize_repository_access
    def backup_to(self, destination: sqlite3.Connection) -> None:
        """Copy this store's consistent SQLite snapshot to a destination."""

        self._connection.backup(destination)

    @_serialize_repository_access
    def healthcheck(self) -> bool:
        """Return whether schema and durable operation values are readable."""

        try:
            integrity = self._connection.execute("PRAGMA integrity_check(1)").fetchone()
            if integrity is None or integrity[0] != "ok":
                return False
            if self._connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                return False
            for row in self._connection.execute("SELECT * FROM operations"):
                self._record(row)
            for row in self._connection.execute("SELECT * FROM operation_events"):
                self._event(row)
            return True
        except (sqlite3.Error, TypeError, ValueError, OverflowError, RecursionError):
            return False

    @_serialize_repository_access
    def _migrate(self) -> None:
        current_version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if current_version > self.SCHEMA_VERSION:
            raise RuntimeError(
                f"operation store schema {current_version} is newer than supported {self.SCHEMA_VERSION}"
            )
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    operation_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    worker_id TEXT,
                    lease_expires_at TEXT,
                    next_run_at TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS operations_eligibility_idx
                    ON operations (state, next_run_at, lease_expires_at)
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS operation_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_id TEXT NOT NULL REFERENCES operations(operation_id),
                    event_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    worker_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS operation_events_operation_idx
                    ON operation_events (operation_id, sequence)
                """
            )
            columns = {
                row[1]
                for row in self._connection.execute("PRAGMA table_info(operations)").fetchall()
            }
            if "cancel_requested" not in columns:
                self._connection.execute(
                    "ALTER TABLE operations ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0"
                )
            self._connection.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
            self._connection.execute("COMMIT")
        except BaseException as error:
            _rollback_after_error(self._connection, error)
            raise

    @_serialize_repository_access
    def create(
        self,
        *,
        operation_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
        now: datetime,
        operation_id: str | None = None,
    ) -> OperationRecord:
        """Create once, or return the identical prior operation by key."""

        _require_text(operation_type, label="operation_type")
        _require_text(idempotency_key, label="idempotency_key")
        _validate_object_payload(payload, label="operation payload")
        if operation_id is None:
            operation_id = str(uuid.uuid4())
        else:
            _require_text(operation_id, label="operation_id")
        timestamp = _utc(now)
        payload_json = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                """
                INSERT INTO operations (
                    operation_id, operation_type, state, idempotency_key,
                    payload_json, checkpoint_json, created_at, updated_at
                ) VALUES (?, ?, 'queued', ?, ?, '{}', ?, ?)
                """,
                (operation_id, operation_type, idempotency_key, payload_json, timestamp, timestamp),
            )
            self._append_event(
                operation_id=operation_id,
                event_type="created",
                state="queued",
                worker_id=None,
                payload={},
                created_at=timestamp,
            )
            self._connection.execute("COMMIT")
        except sqlite3.IntegrityError as error:
            _rollback_after_error(self._connection, error)
            if self._connection.in_transaction:
                raise
            existing = self._by_idempotency(idempotency_key)
            if existing is None:
                raise
            if existing.operation_type != operation_type or existing.payload != payload:
                raise IdempotencyConflict("idempotency key is already bound to another operation")
            return existing
        except BaseException as error:
            _rollback_after_error(self._connection, error)
            raise
        return self.get(operation_id)

    @_serialize_repository_access
    def get(self, operation_id: str) -> OperationRecord:
        _require_text(operation_id, label="operation_id")
        row = self._connection.execute(
            "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        if row is None:
            raise OperationNotFound(operation_id)
        return self._record(row)

    @_serialize_repository_access
    def events(self, operation_id: str) -> tuple[OperationEvent, ...]:
        """Return the immutable audit trail in transition order."""

        _require_text(operation_id, label="operation_id")
        self.get(operation_id)
        rows = self._connection.execute(
            """
            SELECT sequence, operation_id, event_type, state, worker_id, payload_json, created_at
              FROM operation_events
             WHERE operation_id = ?
             ORDER BY sequence ASC
            """,
            (operation_id,),
        ).fetchall()
        return tuple(self._event(row) for row in rows)

    @_serialize_repository_access
    def diagnostic(self, operation_id: str, *, event_limit: int = 100) -> dict[str, Any]:
        return self._diagnostic_views.diagnostic(operation_id, event_limit=event_limit)

    @_serialize_repository_access
    def diagnostics(self, *, limit: int = 50, event_limit: int = 20) -> tuple[dict[str, Any], ...]:
        return self._diagnostic_views.diagnostics(limit=limit, event_limit=event_limit)

    @_serialize_repository_access
    def queue_summary(self, *, now: datetime) -> dict[str, Any]:
        return self._diagnostic_views.queue_summary(now=now)

    @_serialize_repository_access
    def claim(
        self,
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
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
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
            self._connection.execute(
                """
                UPDATE operations
                   SET state = 'running', worker_id = ?, lease_expires_at = ?,
                       next_run_at = NULL, updated_at = ?
                 WHERE operation_id = ?
                """,
                (worker_id, expires_text, now_text, operation_id),
            )
            self._append_event(
                operation_id=operation_id,
                event_type=event_type,
                state="running",
                worker_id=worker_id,
                payload=event_payload,
                created_at=now_text,
            )
            self._connection.execute("COMMIT")
        except BaseException as error:
            _rollback_after_error(self._connection, error)
            raise
        return self.get(operation_id)

    @_serialize_repository_access
    def claim_next(
        self,
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
            self._connection.execute("BEGIN IMMEDIATE")
            # A cancelled worker may have disappeared during an external
            # request. Quarantine one expired lease for explicit resolution;
            # never send it through the ordinary operation handler again.
            uncertain = self._connection.execute(
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
                self._connection.execute(
                    """
                    UPDATE operations
                       SET state = 'waiting_user', checkpoint_json = ?,
                           worker_id = NULL, lease_expires_at = NULL,
                           next_run_at = NULL, updated_at = ?
                     WHERE operation_id = ?
                    """,
                    (checkpoint_json, now_text, operation_id),
                )
                self._append_event(
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
            row = self._connection.execute(
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
                self._connection.execute("COMMIT")
                return None
            operation_id = row["operation_id"]
            recovered = row["state"] == "running"
            event_type = "lease_reclaimed" if recovered else "claimed"
            event_payload = {"lease_expires_at": expires_text}
            if recovered and row["worker_id"]:
                event_payload["previous_worker_id"] = row["worker_id"]
            self._connection.execute(
                """
                UPDATE operations
                   SET state = 'running', worker_id = ?, lease_expires_at = ?,
                       next_run_at = NULL, updated_at = ?
                 WHERE operation_id = ?
                """,
                (worker_id, expires_text, now_text, operation_id),
            )
            self._append_event(
                operation_id=operation_id,
                event_type=event_type,
                state="running",
                worker_id=worker_id,
                payload=event_payload,
                created_at=now_text,
            )
            self._connection.execute("COMMIT")
        except BaseException as error:
            _rollback_after_error(self._connection, error)
            raise
        return self.get(operation_id)

    @_serialize_repository_access
    def renew_lease(
        self,
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
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
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
            self._connection.execute(
                "UPDATE operations SET lease_expires_at = ?, updated_at = ? WHERE operation_id = ?",
                (expires_text, now_text, operation_id),
            )
            self._append_event(
                operation_id=operation_id,
                event_type="lease_renewed",
                state="running",
                worker_id=worker_id,
                payload={"lease_expires_at": expires_text},
                created_at=now_text,
            )
            self._connection.execute("COMMIT")
        except BaseException as error:
            _rollback_after_error(self._connection, error)
            raise
        return self.get(operation_id)

    @_serialize_repository_access
    def checkpoint(
        self,
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
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
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
            self._connection.execute(
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
            self._append_event(
                operation_id=operation_id,
                event_type="checkpointed",
                state=effective_state,
                worker_id=worker_id if effective_state == "running" else None,
                payload=_checkpoint_summary(checkpoint),
                created_at=now_text,
            )
            self._connection.execute("COMMIT")
        except BaseException as error:
            _rollback_after_error(self._connection, error)
            raise
        return self.get(operation_id)

    @_serialize_repository_access
    def cancel(self, operation_id: str, *, now: datetime) -> OperationRecord:
        """Request cooperative cancellation and preserve in-flight ownership."""

        _require_text(operation_id, label="operation_id")
        now_text = _utc(now)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            if row is None:
                raise OperationNotFound(operation_id)
            if row["state"] in {"succeeded", "partial", "failed", "cancelled"}:
                self._connection.execute("COMMIT")
                return self.get(operation_id)
            if row["state"] == "waiting_user" and row["cancel_requested"]:
                # Repeated cancellation is not a resolution of an unknown
                # provider outcome. Preserve the actionable quarantine.
                self._connection.execute("COMMIT")
                return self.get(operation_id)
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
                    self._connection.execute(
                        """
                        UPDATE operations
                           SET checkpoint_json = ?, cancel_requested = 1, updated_at = ?
                         WHERE operation_id = ?
                        """,
                        (checkpoint_json, now_text, operation_id),
                    )
                    self._append_event(
                        operation_id=operation_id,
                        event_type="cancellation_requested",
                        state="waiting_user",
                        worker_id=None,
                        payload={"recovery_reason": "cancelled_while_unknown_outcome"},
                        created_at=now_text,
                    )
                    self._connection.execute("COMMIT")
                    return self.get(operation_id)
            if row["state"] == "running":
                self._connection.execute(
                    "UPDATE operations SET cancel_requested = 1, updated_at = ? WHERE operation_id = ?",
                    (now_text, operation_id),
                )
                self._append_event(
                    operation_id=operation_id,
                    event_type="cancellation_requested",
                    state="running",
                    worker_id=row["worker_id"],
                    payload={},
                    created_at=now_text,
                )
            else:
                self._connection.execute(
                    """
                    UPDATE operations
                       SET state = 'cancelled', worker_id = NULL, lease_expires_at = NULL,
                           cancel_requested = 0, updated_at = ?
                     WHERE operation_id = ?
                    """,
                    (now_text, operation_id),
                )
                self._append_event(
                    operation_id=operation_id,
                    event_type="cancelled",
                    state="cancelled",
                    worker_id=None,
                    payload={},
                    created_at=now_text,
                )
            self._connection.execute("COMMIT")
        except BaseException as error:
            _rollback_after_error(self._connection, error)
            raise
        return self.get(operation_id)

    @_serialize_repository_access
    def resume(self, operation_id: str, *, now: datetime) -> OperationRecord:
        """Re-admit a user-action operation after its external issue is resolved."""

        _require_text(operation_id, label="operation_id")
        now_text = _utc(now)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
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
            self._connection.execute(
                "UPDATE operations SET state = 'queued', updated_at = ? WHERE operation_id = ?",
                (now_text, operation_id),
            )
            self._append_event(
                operation_id=operation_id,
                event_type="resumed",
                state="queued",
                worker_id=None,
                payload={},
                created_at=now_text,
            )
            self._connection.execute("COMMIT")
        except BaseException as error:
            _rollback_after_error(self._connection, error)
            raise
        return self.get(operation_id)

    @_serialize_repository_access
    def resolve_cancelled_outcome(
        self,
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
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
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
            self._connection.execute(
                """
                UPDATE operations
                   SET state = ?, checkpoint_json = ?, cancel_requested = 0,
                       worker_id = NULL, lease_expires_at = NULL,
                       next_run_at = NULL, updated_at = ?
                 WHERE operation_id = ?
                """,
                (resolved_state, checkpoint_json, now_text, operation_id),
            )
            self._append_event(
                operation_id=operation_id,
                event_type="cancellation_reconciled",
                state=resolved_state,
                worker_id=None,
                payload={"outcome": outcome},
                created_at=now_text,
            )
            self._connection.execute("COMMIT")
        except BaseException as error:
            _rollback_after_error(self._connection, error)
            raise
        return self.get(operation_id)

    @_serialize_repository_access
    def schedule_retry(
        self,
        operation_id: str,
        *,
        worker_id: str,
        next_run_at: datetime,
        checkpoint: dict[str, Any],
        now: datetime,
    ) -> OperationRecord:
        """Release a lease and persist a restart-safe retry time."""

        _require_text(operation_id, label="operation_id")
        _require_text(worker_id, label="worker_id")
        _validate_object_payload(checkpoint, label="checkpoint")
        now_text = _utc(now)
        next_run_text = _utc(next_run_at)
        checkpoint_json = json.dumps(
            checkpoint, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            if row is None:
                raise OperationNotFound(operation_id)
            if row["state"] != "running" or row["worker_id"] != worker_id:
                raise LeaseConflict("worker does not own a running operation")
            if row["cancel_requested"]:
                if _checkpoint_requires_reconciliation(checkpoint):
                    self._quarantine_cancelled_outcome(
                        operation_id,
                        checkpoint=checkpoint,
                        recovery_reason="cancelled_during_unknown_outcome",
                        now_text=now_text,
                    )
                    self._connection.execute("COMMIT")
                    return self.get(operation_id)
                self._connection.execute(
                    """
                    UPDATE operations
                       SET state = 'cancelled', checkpoint_json = ?, next_run_at = NULL,
                           worker_id = NULL, lease_expires_at = NULL,
                           cancel_requested = 0, updated_at = ?
                     WHERE operation_id = ?
                    """,
                    (checkpoint_json, now_text, operation_id),
                )
                self._append_event(
                    operation_id=operation_id,
                    event_type="cancelled",
                    state="cancelled",
                    worker_id=None,
                    payload=_checkpoint_summary(checkpoint),
                    created_at=now_text,
                )
                self._connection.execute("COMMIT")
                return self.get(operation_id)
            self._connection.execute(
                """
                UPDATE operations
                   SET state = 'retry_scheduled', checkpoint_json = ?, next_run_at = ?,
                       worker_id = NULL, lease_expires_at = NULL, updated_at = ?
                 WHERE operation_id = ?
                """,
                (checkpoint_json, next_run_text, now_text, operation_id),
            )
            self._append_event(
                operation_id=operation_id,
                event_type="retry_scheduled",
                state="retry_scheduled",
                worker_id=None,
                payload={"next_run_at": next_run_text, **_checkpoint_summary(checkpoint)},
                created_at=now_text,
            )
            self._connection.execute("COMMIT")
        except BaseException as error:
            _rollback_after_error(self._connection, error)
            raise
        return self.get(operation_id)

    @_serialize_repository_access
    def schedule_rate_limit(
        self,
        operation_id: str,
        *,
        worker_id: str,
        next_run_at: datetime,
        checkpoint: dict[str, Any],
        now: datetime,
    ) -> OperationRecord:
        """Release a lease until an absolute provider rate-limit time."""

        _require_text(operation_id, label="operation_id")
        _require_text(worker_id, label="worker_id")
        _validate_object_payload(checkpoint, label="checkpoint")
        now_text = _utc(now)
        next_run_text = _utc(next_run_at)
        checkpoint_json = json.dumps(
            checkpoint, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            if row is None:
                raise OperationNotFound(operation_id)
            if row["state"] != "running" or row["worker_id"] != worker_id:
                raise LeaseConflict("worker does not own a running operation")
            if row["cancel_requested"]:
                if _checkpoint_requires_reconciliation(checkpoint):
                    self._quarantine_cancelled_outcome(
                        operation_id,
                        checkpoint=checkpoint,
                        recovery_reason="cancelled_during_unknown_outcome",
                        now_text=now_text,
                    )
                    self._connection.execute("COMMIT")
                    return self.get(operation_id)
                self._connection.execute(
                    """
                    UPDATE operations
                       SET state = 'cancelled', checkpoint_json = ?, next_run_at = NULL,
                           worker_id = NULL, lease_expires_at = NULL,
                           cancel_requested = 0, updated_at = ?
                     WHERE operation_id = ?
                    """,
                    (checkpoint_json, now_text, operation_id),
                )
                self._append_event(
                    operation_id=operation_id,
                    event_type="cancelled",
                    state="cancelled",
                    worker_id=None,
                    payload=_checkpoint_summary(checkpoint),
                    created_at=now_text,
                )
                self._connection.execute("COMMIT")
                return self.get(operation_id)
            self._connection.execute(
                """
                UPDATE operations
                   SET state = 'waiting_rate_limit', checkpoint_json = ?, next_run_at = ?,
                       worker_id = NULL, lease_expires_at = NULL, updated_at = ?
                 WHERE operation_id = ?
                """,
                (checkpoint_json, next_run_text, now_text, operation_id),
            )
            self._append_event(
                operation_id=operation_id,
                event_type="rate_limit_wait",
                state="waiting_rate_limit",
                worker_id=None,
                payload={"next_run_at": next_run_text, **_checkpoint_summary(checkpoint)},
                created_at=now_text,
            )
            self._connection.execute("COMMIT")
        except BaseException as error:
            _rollback_after_error(self._connection, error)
            raise
        return self.get(operation_id)

    @_serialize_repository_access
    def _by_idempotency(self, idempotency_key: str) -> OperationRecord | None:
        row = self._connection.execute(
            "SELECT * FROM operations WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        return None if row is None else self._record(row)

    def _quarantine_cancelled_outcome(
        self,
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
        self._connection.execute(
            """
            UPDATE operations
               SET state = 'waiting_user', checkpoint_json = ?, next_run_at = NULL,
                   worker_id = NULL, lease_expires_at = NULL, updated_at = ?
             WHERE operation_id = ?
            """,
            (checkpoint_json, now_text, operation_id),
        )
        self._append_event(
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

    @_serialize_repository_access
    def _append_event(
        self,
        *,
        operation_id: str,
        event_type: str,
        state: str,
        worker_id: str | None,
        payload: dict[str, Any],
        created_at: str,
    ) -> None:
        _validate_object_payload(payload, label="operation event payload")
        self._connection.execute(
            """
            INSERT INTO operation_events (
                operation_id, event_type, state, worker_id, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                operation_id,
                event_type,
                state,
                worker_id,
                json.dumps(
                    payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
                ),
                created_at,
            ),
        )

    @staticmethod
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

    @staticmethod
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
