"""Composition root for the dependency-free local runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

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
                repository._connection.execute("SELECT 1").fetchone()  # type: ignore[attr-defined]
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
        if self.database_path != ":memory:" and destination_path != ":memory:":
            if Path(self.database_path).expanduser().resolve() == Path(destination_path).expanduser().resolve():
                raise ValueError("destination_path must differ from the live database")

        destination = sqlite3.connect(destination_path)
        try:
            self.operations._connection.backup(destination)  # type: ignore[attr-defined]
            destination.commit()
        finally:
            destination.close()


__all__ = ["RuntimeResources"]
