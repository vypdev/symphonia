"""Atomic, schema-validated backups for the composed SQLite runtime."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import quote

from symphonia.infrastructure import OperationRepository


def create_backup(
    operations: OperationRepository, database_path: str, destination_path: str,
    healthcheck: Callable[[], bool], validate: Callable[[str], bool],
) -> None:
    """Create a consistent SQLite backup of every composed store.

    All repositories share the operation repository's SQLite file. The
    online-backup API produces a transactionally consistent copy while
    allowing the runtime to keep serving reads and writes. A destination
    must be distinct from the live database; callers decide where the
    resulting backup should be retained.
    """

    if not isinstance(destination_path, str) or not destination_path.strip():
        raise ValueError("destination_path must not be empty")
    if database_path == ":memory:":
        raise ValueError("backups require a persistent database path")
    if destination_path == ":memory:":
        raise ValueError("destination_path must be a persistent filesystem path")
    if not healthcheck():
        raise RuntimeError("cannot back up an unhealthy runtime")
    live_path = Path(database_path).expanduser().resolve()
    destination_candidate = Path(destination_path).expanduser()
    if destination_candidate.is_symlink():
        raise ValueError("destination_path must not be a symbolic link")
    destination_path_object = (
        destination_candidate.parent.resolve() / destination_candidate.name
    )
    if live_path == destination_path_object:
        raise ValueError("destination_path must differ from the live database")
    if not destination_path_object.parent.is_dir():
        raise ValueError("destination_path parent directory must exist")
    if destination_path_object.exists() and destination_path_object.is_dir():
        raise ValueError("destination_path must be a file path")

    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination_path_object.name}.",
            suffix=".tmp",
            dir=destination_path_object.parent,
            delete=False,
        ) as temporary:
            temporary_path = temporary.name
        destination = sqlite3.connect(temporary_path)
        try:
            operations.backup_to(destination)
            destination.commit()
        finally:
            destination.close()
        if not validate(temporary_path):
            raise RuntimeError("SQLite backup integrity validation failed")
        os.replace(temporary_path, destination_path_object)
        temporary_path = None
    except BaseException as backup_error:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            except BaseException as cleanup_error:
                backup_error.add_note(
                    "temporary backup cleanup also failed "
                    f"({type(cleanup_error).__name__})"
                )
        raise

def validate_backup(backup_path: str) -> bool:
    """Validate a backup read-only before a future restore operation."""

    if not isinstance(backup_path, str) or not backup_path.strip():
        raise ValueError("backup_path must not be empty")
    if backup_path == ":memory:":
        return False
    path = Path(backup_path).expanduser().resolve()
    if not path.is_file():
        return False
    uri = f"file:{quote(str(path))}?mode=ro"
    required_tables = {
        "operations",
        "operation_events",
        "copy_plans",
        "provider_connections",
        "authorization_attempts",
        "playlist_snapshots",
        "playlist_snapshot_entries",
        "current_playlist_snapshots",
        "resolution_decisions",
    }
    required_columns = {
        "operations": {
            "operation_id", "operation_type", "state", "idempotency_key",
            "payload_json", "checkpoint_json", "worker_id", "lease_expires_at",
            "next_run_at", "cancel_requested", "created_at", "updated_at",
        },
        "operation_events": {
            "sequence", "operation_id", "event_type", "state", "worker_id",
            "payload_json", "created_at",
        },
        "copy_plans": {"digest", "plan_json", "created_at", "accepted_at"},
        "provider_connections": {
            "connection_id", "provider", "provider_account_id", "state",
            "manifest_version", "secret_ref", "capabilities_json", "expires_at",
            "health_code", "created_at", "updated_at",
        },
        "authorization_attempts": {
            "attempt_id", "provider", "actor_id", "redirect_uri", "state_digest",
            "state", "created_at", "expires_at", "completed_at", "failure_code",
        },
        "playlist_snapshots": {
            "snapshot_id", "provider", "namespace", "playlist_id", "revision", "published_at",
        },
        "playlist_snapshot_entries": {
            "snapshot_id", "occurrence_id", "position", "provider_track_id",
            "provider_track_object_type", "provider_track_title", "source_added_at",
            "provider_track_namespace", "media_kind", "available",
        },
        "current_playlist_snapshots": {"provider", "namespace", "playlist_id", "snapshot_id"},
        "resolution_decisions": {
            "sequence", "decision_id", "provider_track_key", "candidate_recording_id",
            "action", "actor_id", "reason", "created_at", "payload_json",
        },
    }
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(uri, uri=True)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            return False
        operation_schema_version = int(
            connection.execute("PRAGMA user_version").fetchone()[0]
        )
        if operation_schema_version > OperationRepository.SCHEMA_VERSION:
            return False
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if not required_tables.issubset(tables):
            return False
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            return False
        for table, columns in required_columns.items():
            actual_columns = {
                row[1]
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if not columns.issubset(actual_columns):
                return False
        return True
    except sqlite3.Error:
        return False
    finally:
        if connection is not None:
            connection.close()
