"""Durable copy execution against the provider writer port."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from symphonia.domain.models import PlanAcceptanceError
from symphonia.infrastructure.sqlite_operations import OperationRecord, OperationRepository
from symphonia.infrastructure.sqlite_plans import CopyPlanRepository, StoredCopyPlan
from symphonia.providers.writing import PlaylistWriter, ProviderWriteError, WriteOutcome


@dataclass(frozen=True, slots=True)
class CopyExecutionService:
    plans: CopyPlanRepository
    operations: OperationRepository
    retry_delay_seconds: int = 60

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
        stored: StoredCopyPlan,
        operation: OperationRecord,
        *,
        writer: PlaylistWriter,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> OperationRecord:
        digest = stored.plan.digest
        checkpoint = dict(operation.checkpoint)
        if operation.cancel_requested:
            return self._finish(operation, worker_id, checkpoint, now, "cancelled")
        confirmed = list(checkpoint.get("confirmed_occurrences", []))
        issues = list(checkpoint.get("issues", []))
        target_id = checkpoint.get("target_playlist_id")

        if target_id is None:
            if self.operations.get(operation.operation_id).cancel_requested:
                return self._finish(operation, worker_id, checkpoint, now, "cancelled")
            target_key = f"{digest}:target"
            try:
                target = writer.ensure_target_playlist(
                    provider=stored.plan.target_provider,
                    name=stored.plan.target_playlist_name,
                    visibility=stored.plan.target_visibility,
                    idempotency_key=target_key,
                )
            except ProviderWriteError as error:
                if error.outcome is WriteOutcome.RETRYABLE:
                    return self._schedule_retry(operation, worker_id, checkpoint, now)
                if error.outcome is WriteOutcome.RATE_LIMITED:
                    return self._schedule_rate_limit(operation, worker_id, checkpoint, now, error.retry_at)
                if error.outcome is WriteOutcome.UNKNOWN_OUTCOME:
                    target = writer.reconcile_target_playlist(idempotency_key=target_key)
                    if target is None:
                        return self._wait_for_user(operation, worker_id, checkpoint | {"unknown_step": "target"}, now)
                else:
                    issues.append({"step": "target", "detail": error.detail, "provider_code": error.provider_code})
                    return self._finish(operation, worker_id, checkpoint | {"issues": issues}, now, "failed")
            target_id = target.provider_playlist_id
            checkpoint["target_playlist_id"] = target_id
            operation = self.operations.checkpoint(
                operation.operation_id,
                worker_id=worker_id,
                checkpoint=checkpoint,
                now=now,
                state="running",
            )

        for entry in stored.plan.writable_entries:
            if entry.occurrence_id in confirmed:
                continue
            try:
                self.operations.renew_lease(
                    operation.operation_id,
                    worker_id=worker_id,
                    now=now,
                    lease_seconds=lease_seconds,
                )
            except Exception:
                latest = self.operations.get(operation.operation_id)
                if latest.cancel_requested:
                    return self._finish(latest, worker_id, checkpoint, now, "running")
                raise
            step_key = f"{digest}:entry:{entry.occurrence_id}"
            result = writer.add_entry(
                target_playlist_id=target_id,
                provider_track_id=entry.target_track_id or "",
                idempotency_key=step_key,
            )
            if result.outcome is WriteOutcome.UNKNOWN_OUTCOME:
                if writer.reconcile_entry(
                    target_playlist_id=target_id,
                    provider_track_id=entry.target_track_id or "",
                    idempotency_key=step_key,
                ):
                    result = type(result)(WriteOutcome.CONFIRMED_SUCCESS, result.provider_code, result.detail)
                else:
                    return self._wait_for_user(
                        operation,
                        worker_id,
                        checkpoint | {"unknown_step": entry.occurrence_id},
                        now,
                    )
            if result.outcome is WriteOutcome.RETRYABLE:
                return self._schedule_retry(operation, worker_id, checkpoint, now)
            if result.outcome is WriteOutcome.RATE_LIMITED:
                return self._schedule_rate_limit(operation, worker_id, checkpoint, now, result.retry_at)
            if result.outcome is WriteOutcome.PERMANENT_FAILURE:
                issues.append(
                    {
                        "step": entry.occurrence_id,
                        "detail": result.detail or "permanent provider failure",
                        "provider_code": result.provider_code,
                    }
                )
                checkpoint["issues"] = issues
                operation = self.operations.checkpoint(
                    operation.operation_id,
                    worker_id=worker_id,
                    checkpoint=checkpoint,
                    now=now,
                    state="running",
                )
                continue
            confirmed.append(entry.occurrence_id)
            checkpoint["confirmed_occurrences"] = confirmed
            operation = self.operations.checkpoint(
                operation.operation_id,
                worker_id=worker_id,
                checkpoint=checkpoint,
                now=now,
                state="running",
            )

        checkpoint["confirmed_occurrences"] = confirmed
        checkpoint["omitted_occurrences"] = [entry.occurrence_id for entry in stored.plan.omitted_entries]
        checkpoint["issues"] = issues
        terminal = "partial" if stored.plan.omitted_entries or issues else "succeeded"
        return self._finish(operation, worker_id, checkpoint, now, terminal)

    def _finish(
        self,
        operation: OperationRecord,
        worker_id: str,
        checkpoint: dict[str, Any],
        now: datetime,
        state: str,
    ) -> OperationRecord:
        return self.operations.checkpoint(
            operation.operation_id,
            worker_id=worker_id,
            checkpoint=checkpoint,
            now=now,
            state=state,
        )

    def _schedule_retry(
        self,
        operation: OperationRecord,
        worker_id: str,
        checkpoint: dict[str, Any],
        now: datetime,
    ) -> OperationRecord:
        return self.operations.schedule_retry(
            operation.operation_id,
            worker_id=worker_id,
            next_run_at=now + timedelta(seconds=self.retry_delay_seconds),
            checkpoint=checkpoint,
            now=now,
        )

    def _schedule_rate_limit(
        self,
        operation: OperationRecord,
        worker_id: str,
        checkpoint: dict[str, Any],
        now: datetime,
        retry_at: datetime | None,
    ) -> OperationRecord:
        next_run_at = retry_at if retry_at is not None and retry_at > now else now + timedelta(seconds=self.retry_delay_seconds)
        return self.operations.schedule_rate_limit(
            operation.operation_id,
            worker_id=worker_id,
            next_run_at=next_run_at,
            checkpoint=checkpoint,
            now=now,
        )

    def _wait_for_user(
        self,
        operation: OperationRecord,
        worker_id: str,
        checkpoint: dict[str, Any],
        now: datetime,
    ) -> OperationRecord:
        return self.operations.checkpoint(
            operation.operation_id,
            worker_id=worker_id,
            checkpoint=checkpoint,
            now=now,
            state="waiting_user",
        )
