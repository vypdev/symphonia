"""Transactional SQLite state machine for durable operations and worker leases."""

from __future__ import annotations

from datetime import datetime
import json
import sqlite3
from threading import RLock
from typing import Any
import uuid

from symphonia.domain.operations import LeaseConflict, OperationEvent, OperationRecord

from .sqlite_common import connect, initialize_with_cleanup
from .sqlite_operation_codec import _event, _record, _require_text, _utc, _validate_object_payload
from .sqlite_operation_claims import claim, claim_next, renew_lease
from .sqlite_operation_context import OperationContext
from .sqlite_operation_diagnostics import OperationDiagnostics
from .sqlite_operation_rules import IdempotencyConflict, OperationNotFound
from .sqlite_operation_scheduling import schedule_rate_limit, schedule_retry
from .sqlite_operation_schema import migrate_operations
from .sqlite_operation_transactions import _rollback_after_error, _serialize_repository_access
from .sqlite_operation_transitions import (
    cancel,
    checkpoint as persist_checkpoint,
    resolve_cancelled_outcome,
    resume,
)


class OperationRepository:
    """Transactional operation repository backed by one SQLite database."""

    SCHEMA_VERSION = 3

    def __init__(self, path: str = ":memory:") -> None:
        self._connection_lock = RLock()
        self._connection = connect(path)
        initialize_with_cleanup(self._connection, self._migrate)
        self._diagnostic_views = OperationDiagnostics(self._connection, self.get, _event)
        self._context = OperationContext(self._connection, self.get, self._append_event)

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
                _record(row)
            for row in self._connection.execute("SELECT * FROM operation_events"):
                _event(row)
            return True
        except (sqlite3.Error, TypeError, ValueError, OverflowError, RecursionError):
            return False

    @_serialize_repository_access
    def _migrate(self) -> None:
        migrate_operations(self._connection, self.SCHEMA_VERSION)

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
        return _record(row)

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
        return tuple(_event(row) for row in rows)

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
        self, operation_id: str, *, worker_id: str, now: datetime,
        lease_seconds: int = 30,
    ) -> OperationRecord:
        return claim(
            self._context, operation_id, worker_id=worker_id,
            now=now, lease_seconds=lease_seconds,
        )

    @_serialize_repository_access
    def claim_next(
        self, *, worker_id: str, now: datetime, lease_seconds: int = 30,
        operation_type: str | None = None,
    ) -> OperationRecord | None:
        return claim_next(
            self._context, worker_id=worker_id, now=now,
            lease_seconds=lease_seconds, operation_type=operation_type,
        )

    @_serialize_repository_access
    def renew_lease(
        self, operation_id: str, *, worker_id: str, now: datetime,
        lease_seconds: int = 30,
    ) -> OperationRecord:
        return renew_lease(
            self._context, operation_id, worker_id=worker_id,
            now=now, lease_seconds=lease_seconds,
        )

    @_serialize_repository_access
    def checkpoint(
        self, operation_id: str, *, worker_id: str, checkpoint: dict[str, Any],
        now: datetime, state: str = "running",
    ) -> OperationRecord:
        return persist_checkpoint(
            self._context, operation_id, worker_id=worker_id, checkpoint=checkpoint,
            now=now, state=state,
        )

    @_serialize_repository_access
    def cancel(self, operation_id: str, *, now: datetime) -> OperationRecord:
        return cancel(self._context, operation_id, now=now)

    @_serialize_repository_access
    def resume(self, operation_id: str, *, now: datetime) -> OperationRecord:
        return resume(self._context, operation_id, now=now)

    @_serialize_repository_access
    def resolve_cancelled_outcome(
        self, operation_id: str, *, outcome: str, now: datetime,
    ) -> OperationRecord:
        return resolve_cancelled_outcome(
            self._context, operation_id, outcome=outcome, now=now,
        )

    @_serialize_repository_access
    def schedule_retry(
        self, operation_id: str, *, worker_id: str, next_run_at: datetime,
        checkpoint: dict[str, Any], now: datetime,
    ) -> OperationRecord:
        return schedule_retry(
            self._context, operation_id, worker_id=worker_id, next_run_at=next_run_at,
            checkpoint=checkpoint, now=now,
        )

    @_serialize_repository_access
    def schedule_rate_limit(
        self, operation_id: str, *, worker_id: str, next_run_at: datetime,
        checkpoint: dict[str, Any], now: datetime,
    ) -> OperationRecord:
        return schedule_rate_limit(
            self._context, operation_id, worker_id=worker_id, next_run_at=next_run_at,
            checkpoint=checkpoint, now=now,
        )

    @_serialize_repository_access
    def _by_idempotency(self, idempotency_key: str) -> OperationRecord | None:
        row = self._connection.execute(
            "SELECT * FROM operations WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        return None if row is None else _record(row)

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
