"""Composition root for the dependency-free local runtime."""

from __future__ import annotations

from dataclasses import dataclass

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
        return cls(operations, plans, connections, authorization, projections, resolutions)

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


__all__ = ["RuntimeResources"]
