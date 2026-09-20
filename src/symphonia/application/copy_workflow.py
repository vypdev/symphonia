"""Application orchestration for planning and admitting a copy operation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from symphonia.domain.models import CopyPlan, CopyPolicy, PlanAcceptanceError, PlaylistSnapshot
from symphonia.infrastructure.sqlite_operations import OperationRecord, OperationRepository
from symphonia.infrastructure.sqlite_plans import CopyPlanRepository, StoredCopyPlan

from .copy_planning import CopyPlanningService


@dataclass(frozen=True, slots=True)
class CopyWorkflowService:
    """Keep plan persistence/acceptance separate from provider execution."""

    planning: CopyPlanningService
    plans: CopyPlanRepository
    operations: OperationRepository

    def create_plan(
        self,
        snapshot: PlaylistSnapshot,
        *,
        target_provider: str,
        target_playlist_name: str,
        target_visibility: str,
        policy: CopyPolicy,
        now: datetime,
    ) -> StoredCopyPlan:
        plan = self.planning.plan(
            snapshot,
            target_provider=target_provider,
            target_playlist_name=target_playlist_name,
            target_visibility=target_visibility,
            policy=policy,
        )
        return self.plans.save(plan, now=now)

    def accept_plan(self, digest: str, *, now: datetime) -> StoredCopyPlan:
        return self.plans.accept(digest, expected_digest=digest, now=now)

    def enqueue_accepted_plan(self, digest: str, *, now: datetime) -> OperationRecord:
        stored = self.plans.get(digest)
        if stored.accepted_at is None:
            raise PlanAcceptanceError("copy plan must be accepted before it can be enqueued")
        return self.operations.create(
            operation_type="copy_playlist",
            idempotency_key=f"copy-plan:{digest}",
            payload={"plan_digest": digest},
            now=now,
        )

