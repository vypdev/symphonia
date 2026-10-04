"""Composition root for the dependency-free local runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from symphonia.infrastructure import (
    AuthorizationAttemptRepository,
    CopyPlanRepository,
    OperationRepository,
    PlaylistProjectionRepository,
    ProviderConnectionRepository,
    ResolutionDecisionRepository,
)
from .backup import create_backup, validate_backup
from .config import normalize_database_path


class _ClosableRepository(Protocol):
    def close(self) -> None: ...


def _close_after_startup_failure(
    opened: list[_ClosableRepository], startup_error: BaseException,
) -> None:
    """Close partial startup in reverse order without replacing its cause."""

    cleanup_error_types: list[str] = []
    for repository in reversed(opened):
        try:
            repository.close()
        except BaseException as cleanup_error:
            cleanup_error_types.append(type(cleanup_error).__name__)
    if cleanup_error_types:
        error_types = ", ".join(cleanup_error_types)
        startup_error.add_note(
            "startup cleanup also encountered repository close errors "
            f"({error_types})"
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
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    def open(cls, database_path: str) -> "RuntimeResources":
        database_path = normalize_database_path(database_path)
        opened: list[_ClosableRepository] = []
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
        except BaseException as startup_error:
            _close_after_startup_failure(opened, startup_error)
            raise
        return cls(operations, plans, connections, authorization, projections, resolutions, database_path)

    def close(self) -> None:
        """Close repositories in reverse dependency/startup order."""

        if self._closed:
            return
        first_error: BaseException | None = None
        for repository in (
            self.resolutions,
            self.projections,
            self.authorization,
            self.connections,
            self.plans,
            self.operations,
        ):
            try:
                repository.close()
            except BaseException as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error
        self._closed = True

    def __enter__(self) -> "RuntimeResources":
        return self

    def __exit__(self, _exception_type: object, _exception: object, _traceback: object) -> None:
        self.close()

    def healthcheck(self) -> bool:
        """Check every durable store without exposing adapter internals."""

        if self._closed:
            return False
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
        """Create an atomic backup of all composed stores."""
        create_backup(
            self.operations, self.database_path, destination_path,
            self.healthcheck, self.validate_backup,
        )

    @classmethod
    def validate_backup(cls, backup_path: str) -> bool:
        """Validate a backup read-only before a future restore operation."""
        return validate_backup(backup_path)

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
        if operation_limit > 100 or event_limit > 100:
            raise ValueError("diagnostic limits must not exceed 100")
        try:
            if not self.healthcheck():
                return {"ready": False}
            return {
                "ready": True,
                "queue": self.operations.queue_summary(now=now),
                "connections": self.connections.health_summary(now=now),
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
