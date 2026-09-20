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
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OperationEvent:
    """Append-only audit record for an operation state transition."""

    sequence: int
    operation_id: str
    event_type: str
    state: str
    worker_id: str | None
    payload: dict[str, Any]
    created_at: datetime


class OperationRepository:
    """Transactional operation repository backed by one SQLite database."""

    SCHEMA_VERSION = 3

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
        current_version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if current_version > self.SCHEMA_VERSION:
            raise RuntimeError(
                f"operation store schema {current_version} is newer than supported {self.SCHEMA_VERSION}"
            )
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
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS operations_eligibility_idx
                ON operations (state, next_run_at, lease_expires_at);
            CREATE TABLE IF NOT EXISTS operation_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id TEXT NOT NULL REFERENCES operations(operation_id),
                event_type TEXT NOT NULL,
                state TEXT NOT NULL,
                worker_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS operation_events_operation_idx
                ON operation_events (operation_id, sequence);
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
        self._connection.execute("BEGIN IMMEDIATE")
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
            self._append_event(
                operation_id=operation_id,
                event_type="created",
                state="queued",
                worker_id=None,
                payload={},
                created_at=timestamp,
            )
            self._connection.execute("COMMIT")
        except sqlite3.IntegrityError:
            self._connection.execute("ROLLBACK")
            existing = self._by_idempotency(idempotency_key)
            if existing is None:
                raise
            if existing.operation_type != operation_type or existing.payload != payload:
                raise IdempotencyConflict("idempotency key is already bound to another operation")
            return existing
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return self.get(operation_id)

    def get(self, operation_id: str) -> OperationRecord:
        row = self._connection.execute(
            "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        if row is None:
            raise OperationNotFound(operation_id)
        return self._record(row)

    def events(self, operation_id: str) -> tuple[OperationEvent, ...]:
        """Return the immutable audit trail in transition order."""

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

    def diagnostic(self, operation_id: str, *, event_limit: int = 100) -> dict[str, Any]:
        """Return a bounded, redacted support view of one operation."""

        if event_limit <= 0:
            raise ValueError("event_limit must be positive")
        record = self.get(operation_id)
        all_events = self.events(operation_id)
        selected_events = all_events[-event_limit:]
        return {
            "operation_id": record.operation_id,
            "operation_type": record.operation_type,
            "state": record.state,
            "worker_id": record.worker_id,
            "next_run_at": None if record.next_run_at is None else _utc(record.next_run_at),
            "cancel_requested": record.cancel_requested,
            "created_at": _utc(record.created_at),
            "updated_at": _utc(record.updated_at),
            "payload_keys": sorted(str(key) for key in record.payload),
            "checkpoint": self._checkpoint_summary(record.checkpoint),
            "events_truncated": len(selected_events) != len(all_events),
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

        if limit <= 0:
            raise ValueError("limit must be positive")
        if event_limit <= 0:
            raise ValueError("event_limit must be positive")
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
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return self.get(operation_id)

    def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 30,
        operation_type: str | None = None,
    ) -> OperationRecord | None:
        """Atomically claim the oldest queued, due, or expired operation.

        This is the scheduler-facing primitive. It deliberately selects only
        durable eligibility; handler dispatch remains an application concern.
        """

        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now_text = _utc(now)
        expires_text = _utc(now + timedelta(seconds=lease_seconds))
        type_clause = " AND operation_type = ?" if operation_type is not None else ""
        parameters: tuple[Any, ...] = (now_text, now_text)
        if operation_type is not None:
            parameters += (operation_type,)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
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
            self._append_event(
                operation_id=operation_id,
                event_type="lease_renewed",
                state="running",
                worker_id=worker_id,
                payload={"lease_expires_at": expires_text},
                created_at=now_text,
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
            effective_state = "cancelled" if row["cancel_requested"] else state
            self._connection.execute(
                """
                UPDATE operations
                   SET state = ?, checkpoint_json = ?, updated_at = ?,
                       worker_id = CASE WHEN ? = 'running' THEN worker_id ELSE NULL END,
                       lease_expires_at = CASE WHEN ? = 'running' THEN lease_expires_at ELSE NULL END,
                       cancel_requested = CASE WHEN ? = 'cancelled' THEN 0 ELSE cancel_requested END
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
                payload=self._checkpoint_summary(checkpoint),
                created_at=now_text,
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return self.get(operation_id)

    def cancel(self, operation_id: str, *, now: datetime) -> OperationRecord:
        """Request cooperative cancellation and preserve in-flight ownership."""

        now_text = _utc(now)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            if row is None:
                raise OperationNotFound(operation_id)
            if row["state"] in {"succeeded", "partial", "failed", "cancelled"}:
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
            self._append_event(
                operation_id=operation_id,
                event_type="resumed",
                state="queued",
                worker_id=None,
                payload={},
                created_at=now_text,
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
            if row["cancel_requested"]:
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
                    payload=self._checkpoint_summary(checkpoint),
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
                payload={"next_run_at": next_run_text, **self._checkpoint_summary(checkpoint)},
                created_at=now_text,
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return self.get(operation_id)

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
            if row["cancel_requested"]:
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
                    payload=self._checkpoint_summary(checkpoint),
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
                payload={"next_run_at": next_run_text, **self._checkpoint_summary(checkpoint)},
                created_at=now_text,
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
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                created_at,
            ),
        )

    @staticmethod
    def _checkpoint_summary(checkpoint: dict[str, Any]) -> dict[str, Any]:
        """Keep audit data useful while excluding checkpoint values by default."""

        summary: dict[str, Any] = {
            "checkpoint_keys": sorted(str(key) for key in checkpoint),
        }
        for key in ("confirmed_occurrences", "issues"):
            value = checkpoint.get(key)
            if isinstance(value, (list, tuple, set)):
                summary[f"{key}_count"] = len(value)
        return summary

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
            cancel_requested=bool(row["cancel_requested"]),
            created_at=_parse_utc(row["created_at"]),
            updated_at=_parse_utc(row["updated_at"]),
        )

    @staticmethod
    def _event(row: sqlite3.Row) -> OperationEvent:
        return OperationEvent(
            sequence=row["sequence"],
            operation_id=row["operation_id"],
            event_type=row["event_type"],
            state=row["state"],
            worker_id=row["worker_id"],
            payload=json.loads(row["payload_json"]),
            created_at=_parse_utc(row["created_at"]),
        )
