"""Atomic creation and forward migration of the operation store schema."""

from __future__ import annotations

import sqlite3

from .sqlite_operation_transactions import _rollback_after_error


def migrate_operations(connection: sqlite3.Connection, schema_version: int) -> None:
    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version > schema_version:
        raise RuntimeError(
            f"operation store schema {current_version} is newer than supported {schema_version}"
        )
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
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
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS operations_eligibility_idx
                ON operations (state, next_run_at, lease_expires_at)
            """
        )
        connection.execute(
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
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS operation_events_operation_idx
                ON operation_events (operation_id, sequence)
            """
        )
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(operations)").fetchall()
        }
        if "cancel_requested" not in columns:
            connection.execute(
                "ALTER TABLE operations ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0"
            )
        connection.execute(f"PRAGMA user_version = {schema_version}")
        connection.execute("COMMIT")
    except BaseException as error:
        _rollback_after_error(connection, error)
        raise

