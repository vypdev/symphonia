"""Composition root for the dependency-free local runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import quote

from symphonia.infrastructure import (
    AuthorizationAttemptRepository,
    CopyPlanRepository,
    OperationRepository,
    PlaylistProjectionRepository,
    ProviderConnectionRepository,
    ResolutionDecisionRepository,
)


@dataclass(slots=True)
class RuntimeResources:
    """Own every durable repository opened by one Symphonia process.

    Repositories intentionally remain separate adapters for now. They point
    at the same SQLite path in a persistent runtime, while this owner gives
    startup/shutdown one explicit lifecycle boundary and leaves room for a
    future shared transaction adapter.
    """

    operations: OperationRepository
    plans: CopyPlanRepository
    connections: ProviderConnectionRepository
    authorization: AuthorizationAttemptRepository
    projections: PlaylistProjectionRepository
    resolutions: ResolutionDecisionRepository
    database_path: str = ":memory:"

    @classmethod
    def open(cls, database_path: str) -> "RuntimeResources":
        if not database_path.strip():
            raise ValueError("database_path must not be empty")
        opened: list[object] = []
        try:
            operations = OperationRepository(database_path)
            opened.append(operations)
            plans = CopyPlanRepository(database_path)
            opened.append(plans)
            connections = ProviderConnectionRepository(database_path)
            opened.append(connections)
            authorization = AuthorizationAttemptRepository(database_path)
            opened.append(authorization)
            projections = PlaylistProjectionRepository(database_path)
            opened.append(projections)
            resolutions = ResolutionDecisionRepository(database_path)
            opened.append(resolutions)
        except Exception:
            for repository in reversed(opened):
                repository.close()  # type: ignore[attr-defined]
            raise
        return cls(operations, plans, connections, authorization, projections, resolutions, database_path)

    def close(self) -> None:
        """Close repositories in reverse dependency/startup order."""

        for repository in (
            self.resolutions,
            self.projections,
            self.authorization,
            self.connections,
            self.plans,
            self.operations,
        ):
            repository.close()

    def healthcheck(self) -> bool:
        """Check every durable store without exposing adapter internals."""

        try:
            for repository in (
                self.operations,
                self.plans,
                self.connections,
                self.authorization,
                self.projections,
                self.resolutions,
            ):
                if not repository.healthcheck():
                    return False
        except Exception:
            return False
        return True

    def backup_to(self, destination_path: str) -> None:
        """Create a consistent SQLite backup of every composed store.

        All repositories share the operation repository's SQLite file. The
        online-backup API produces a transactionally consistent copy while
        allowing the runtime to keep serving reads and writes. A destination
        must be distinct from the live database; callers decide where the
        resulting backup should be retained.
        """

        if not destination_path.strip():
            raise ValueError("destination_path must not be empty")
        if not self.healthcheck():
            raise RuntimeError("cannot back up an unhealthy runtime")
        if self.database_path != ":memory:" and destination_path != ":memory:":
            if Path(self.database_path).expanduser().resolve() == Path(destination_path).expanduser().resolve():
                raise ValueError("destination_path must differ from the live database")

        destination = sqlite3.connect(destination_path)
        try:
            self.operations._connection.backup(destination)  # type: ignore[attr-defined]
            destination.commit()
        finally:
            destination.close()

    @classmethod
    def validate_backup(cls, backup_path: str) -> bool:
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
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(uri, uri=True)
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                return False
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            return required_tables.issubset(tables)
        except sqlite3.Error:
            return False
        finally:
            if connection is not None:
                connection.close()

    def diagnostics(
        self,
        *,
        now: datetime,
        operation_limit: int = 50,
        event_limit: int = 20,
    ) -> dict[str, Any]:
        """Return a bounded support view without database paths or payloads."""

        if operation_limit <= 0:
            raise ValueError("operation_limit must be positive")
        if event_limit <= 0:
            raise ValueError("event_limit must be positive")
        try:
            if not self.healthcheck():
                return {"ready": False}
            return {
                "ready": True,
                "queue": self.operations.queue_summary(now=now),
                "connections": self.connections.health_summary(),
                "projections": self.projections.summary(),
                "resolutions": self.resolutions.summary(),
                "operations": self.operations.diagnostics(
                    limit=operation_limit,
                    event_limit=event_limit,
                ),
            }
        except Exception:
            # A concurrent close or adapter failure must not expose internals
            # or make a support endpoint look healthier than the stores are.
            return {"ready": False}


__all__ = ["RuntimeResources"]
