"""Durable copy execution against the provider writer port."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from symphonia.domain.models import PlanAcceptanceError
from symphonia.domain.plans import CopyPlanRecord
from symphonia.domain.operations import OperationRecord
from symphonia.providers.writing import PlaylistWriter

from .copy_checkpoint import parse_copy_progress
from .copy_execution_entries import copy_entries
from .copy_execution_state import CopyRun
from .copy_execution_target import ensure_target
from .ports import CopyPlanPort, OperationPort


@dataclass(frozen=True, slots=True)
class CopyExecutionService:
    plans: CopyPlanPort
    operations: OperationPort
    retry_delay_seconds: int = 60
    max_retry_attempts: int = 5

    def __post_init__(self) -> None:
        if self.retry_delay_seconds <= 0:
            raise ValueError("retry_delay_seconds must be positive")
        if self.max_retry_attempts < 0:
            raise ValueError("max_retry_attempts must not be negative")

    def execute(
        self,
        digest: str,
        *,
        writer: PlaylistWriter,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 30,
    ) -> OperationRecord:
        stored = self.plans.get(digest)
        if stored.accepted_at is None:
            raise PlanAcceptanceError("copy plan must be accepted before execution")
        operation = self.operations.create(
            operation_type="copy_playlist",
            idempotency_key=f"copy-plan:{digest}",
            payload={"plan_digest": digest},
            now=now,
        )
        if operation.state in {"succeeded", "partial", "failed", "cancelled"}:
            return operation
        operation = self.operations.claim(
            operation.operation_id,
            worker_id=worker_id,
            now=now,
            lease_seconds=lease_seconds,
        )
        return self._execute_claimed(
            stored,
            operation,
            writer=writer,
            worker_id=worker_id,
            now=now,
            lease_seconds=lease_seconds,
        )

    def execute_claimed(
        self,
        operation: OperationRecord,
        *,
        writer: PlaylistWriter,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 30,
    ) -> OperationRecord:
        """Continue a copy operation already claimed by an operation runner."""

        if operation.state != "running" or operation.worker_id != worker_id:
            raise ValueError("copy operation must be running under the supplied worker")
        digest = operation.payload.get("plan_digest")
        if not isinstance(digest, str) or not digest.strip():
            raise PlanAcceptanceError("copy operation payload has no plan digest")
        stored = self.plans.get(digest)
        if stored.accepted_at is None:
            raise PlanAcceptanceError("copy plan must be accepted before execution")
        return self._execute_claimed(
            stored,
            operation,
            writer=writer,
            worker_id=worker_id,
            now=now,
            lease_seconds=lease_seconds,
        )

    def _execute_claimed(
        self,
        stored: CopyPlanRecord,
        operation: OperationRecord,
        *,
        writer: PlaylistWriter,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> OperationRecord:
        checkpoint = dict(operation.checkpoint)
        if operation.cancel_requested:
            return self.operations.checkpoint(
                operation.operation_id,
                worker_id=worker_id,
                checkpoint=checkpoint,
                now=now,
                state="cancelled",
            )
        progress = parse_copy_progress(stored.plan, checkpoint)
        if isinstance(progress, str):
            return self.operations.checkpoint(
                operation.operation_id,
                worker_id=worker_id,
                checkpoint=checkpoint | {"failure_code": progress},
                now=now,
                state="waiting_user",
            )
        run = CopyRun(
            operations=self.operations,
            writer=writer,
            stored=stored,
            operation=operation,
            worker_id=worker_id,
            now=now,
            lease_seconds=lease_seconds,
            retry_delay_seconds=self.retry_delay_seconds,
            max_retry_attempts=self.max_retry_attempts,
            checkpoint=checkpoint,
            progress=progress,
        )
        stopped = ensure_target(run)
        return stopped if stopped is not None else copy_entries(run)
