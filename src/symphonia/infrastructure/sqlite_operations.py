"""SQLite persistence for durable operation state.

This adapter is deliberately small: it proves the transaction/lease contract
needed by the durable-operations SDD before provider handlers and a scheduler
are introduced. The database is the authority; worker memory is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Any
import uuid


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class OperationNotFound(LookupError):
    pass


class IdempotencyConflict(ValueError):
    pass


class LeaseConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OperationRecord:
    operation_id: str
    operation_type: str
    state: str
    idempotency_key: str
    payload: dict[str, Any]
    checkpoint: dict[str, Any]
    worker_id: str | None
    lease_expires_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OperationRepository:
    """Transactional operation repository backed by one SQLite database."""

    def __init__(self, path: str = ":memory:") -> None:
        self._connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._migrate()

    def close(self) -> None:
        self._connection.close()

    def healthcheck(self) -> bool:
        """Return whether the migrated store can answer a basic read."""

        row = self._connection.execute("SELECT 1 AS healthy").fetchone()
        return row is not None and row["healthy"] == 1

    def _migrate(self) -> None:
        self._connection.executescript(
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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS operations_eligibility_idx
                ON operations (state, next_run_at, lease_expires_at);
            """
        )

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

        if not operation_type.strip() or not idempotency_key.strip():
            raise ValueError("operation_type and idempotency_key must not be empty")
        operation_id = operation_id or str(uuid.uuid4())
        timestamp = _utc(now)
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        try:
            self._connection.execute(
                """
                INSERT INTO operations (
                    operation_id, operation_type, state, idempotency_key,
                    payload_json, checkpoint_json, created_at, updated_at
                ) VALUES (?, ?, 'queued', ?, ?, '{}', ?, ?)
                """,
                (operation_id, operation_type, idempotency_key, payload_json, timestamp, timestamp),
            )
        except sqlite3.IntegrityError:
            existing = self._by_idempotency(idempotency_key)
            if existing is None:
                raise
            if existing.operation_type != operation_type or existing.payload != payload:
                raise IdempotencyConflict("idempotency key is already bound to another operation")
            return existing
        return self.get(operation_id)

    def get(self, operation_id: str) -> OperationRecord:
        row = self._connection.execute(
            "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        if row is None:
            raise OperationNotFound(operation_id)
        return self._record(row)

    def claim(
        self,
        operation_id: str,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 30,
    ) -> OperationRecord:
        """Claim queued/retryable work or reclaim a lease that has expired."""

        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now_text = _utc(now)
        expires_text = _utc(now + timedelta(seconds=lease_seconds))
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            if row is None:
                raise OperationNotFound(operation_id)
            eligible = row["state"] == "queued" or (
                row["state"] == "retry_scheduled"
                and row["next_run_at"] is not None
                and row["next_run_at"] <= now_text
            )
            expired = row["state"] == "running" and (
                row["lease_expires_at"] is None or row["lease_expires_at"] <= now_text
            )
            if not eligible and not expired:
                raise LeaseConflict(f"operation {operation_id} is not eligible for claim")
            self._connection.execute(
                """
                UPDATE operations
                   SET state = 'running', worker_id = ?, lease_expires_at = ?,
                       next_run_at = NULL, updated_at = ?
                 WHERE operation_id = ?
                """,
                (worker_id, expires_text, now_text, operation_id),
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return self.get(operation_id)

    def renew_lease(
        self,
        operation_id: str,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 30,
    ) -> OperationRecord:
        """Extend a healthy lease; an expired owner cannot resurrect it."""

        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now_text = _utc(now)
        expires_text = _utc(now + timedelta(seconds=lease_seconds))
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            if row is None:
                raise OperationNotFound(operation_id)
            if row["state"] != "running" or row["worker_id"] != worker_id:
                raise LeaseConflict("worker does not own a running operation")
            if row["lease_expires_at"] is not None and row["lease_expires_at"] <= now_text:
                raise LeaseConflict("operation lease has expired")
            self._connection.execute(
                "UPDATE operations SET lease_expires_at = ?, updated_at = ? WHERE operation_id = ?",
                (expires_text, now_text, operation_id),
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return self.get(operation_id)

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

        if state not in {"running", "succeeded", "partial", "failed", "cancelled", "waiting_user"}:
            raise ValueError("invalid checkpoint state")
        now_text = _utc(now)
        checkpoint_json = json.dumps(checkpoint, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            if row is None:
                raise OperationNotFound(operation_id)
            if row["state"] != "running" or row["worker_id"] != worker_id:
                raise LeaseConflict("worker does not own a running operation")
            if row["lease_expires_at"] is not None and row["lease_expires_at"] <= now_text:
                raise LeaseConflict("operation lease has expired")
            self._connection.execute(
                """
                UPDATE operations
                   SET state = ?, checkpoint_json = ?, updated_at = ?,
                       worker_id = CASE WHEN ? = 'running' THEN worker_id ELSE NULL END,
                       lease_expires_at = CASE WHEN ? = 'running' THEN lease_expires_at ELSE NULL END
                 WHERE operation_id = ?
                """,
                (state, checkpoint_json, now_text, state, state, operation_id),
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return self.get(operation_id)

    def resume(self, operation_id: str, *, now: datetime) -> OperationRecord:
        """Re-admit a user-action operation after its external issue is resolved."""

        now_text = _utc(now)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            if row is None:
                raise OperationNotFound(operation_id)
            if row["state"] != "waiting_user":
                raise LeaseConflict("only waiting_user operations can be resumed")
            self._connection.execute(
                "UPDATE operations SET state = 'queued', updated_at = ? WHERE operation_id = ?",
                (now_text, operation_id),
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return self.get(operation_id)

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

        now_text = _utc(now)
        next_run_text = _utc(next_run_at)
        checkpoint_json = json.dumps(checkpoint, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            if row is None:
                raise OperationNotFound(operation_id)
            if row["state"] != "running" or row["worker_id"] != worker_id:
                raise LeaseConflict("worker does not own a running operation")
            self._connection.execute(
                """
                UPDATE operations
                   SET state = 'retry_scheduled', checkpoint_json = ?, next_run_at = ?,
                       worker_id = NULL, lease_expires_at = NULL, updated_at = ?
                 WHERE operation_id = ?
                """,
                (checkpoint_json, next_run_text, now_text, operation_id),
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return self.get(operation_id)

    def _by_idempotency(self, idempotency_key: str) -> OperationRecord | None:
        row = self._connection.execute(
            "SELECT * FROM operations WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        return None if row is None else self._record(row)

    @staticmethod
    def _record(row: sqlite3.Row) -> OperationRecord:
        return OperationRecord(
            operation_id=row["operation_id"],
            operation_type=row["operation_type"],
            state=row["state"],
            idempotency_key=row["idempotency_key"],
            payload=json.loads(row["payload_json"]),
            checkpoint=json.loads(row["checkpoint_json"]),
            worker_id=row["worker_id"],
            lease_expires_at=None if row["lease_expires_at"] is None else _parse_utc(row["lease_expires_at"]),
            next_run_at=None if row["next_run_at"] is None else _parse_utc(row["next_run_at"]),
            created_at=_parse_utc(row["created_at"]),
            updated_at=_parse_utc(row["updated_at"]),
        )
