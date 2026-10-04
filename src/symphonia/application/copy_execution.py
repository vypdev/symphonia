"""Durable copy execution against the provider writer port."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from symphonia.domain.models import PlanAcceptanceError
from symphonia.domain.plans import CopyPlanRecord
from symphonia.domain.operations import LeaseConflict, OperationRecord
from symphonia.providers.writing import PlaylistWriter, ProviderWriteError, WriteOutcome

from .copy_checkpoint import parse_copy_progress
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
        digest = stored.plan.digest
        checkpoint = dict(operation.checkpoint)
        if operation.cancel_requested:
            return self._finish(operation, worker_id, checkpoint, now, "cancelled")
        progress = parse_copy_progress(stored.plan, checkpoint)
        if isinstance(progress, str):
            return self._wait_for_user(
                operation, worker_id, checkpoint | {"failure_code": progress}, now
            )
        writable_entries = stored.plan.writable_entries
        confirmed = progress.confirmed
        confirmed_ids = progress.confirmed_ids
        issues = progress.issues
        failed_steps = progress.failed_steps
        target_id = progress.target_id
        unknown_step = progress.unknown_step

        target_key = f"{digest}:target"
        if unknown_step == "target":
            stopped = self._renew_or_stop(
                operation,
                worker_id,
                checkpoint,
                now,
                lease_seconds,
            )
            if stopped is not None:
                return stopped
            try:
                target = writer.reconcile_target_playlist(idempotency_key=target_key)
            except Exception:
                return self._wait_for_user(operation, worker_id, checkpoint, now)
            if target is None or (target_id is not None and target.provider_playlist_id != target_id):
                return self._wait_for_user(operation, worker_id, checkpoint, now)
            target_id = target.provider_playlist_id
            checkpoint["target_playlist_id"] = target_id
            checkpoint.pop("unknown_step", None)
            operation = self.operations.checkpoint(
                operation.operation_id,
                worker_id=worker_id,
                checkpoint=checkpoint,
                now=now,
                state="running",
            )
            if operation.state != "running":
                return operation
            unknown_step = None

        if target_id is None:
            stopped = self._renew_or_stop(
                operation,
                worker_id,
                checkpoint,
                now,
                lease_seconds,
            )
            if stopped is not None:
                return stopped
            checkpoint["unknown_step"] = "target"
            operation = self.operations.checkpoint(
                operation.operation_id,
                worker_id=worker_id,
                checkpoint=checkpoint,
                now=now,
                state="running",
            )
            if operation.state != "running":
                return operation
            stopped = self._renew_or_stop(
                operation,
                worker_id,
                checkpoint,
                now,
                lease_seconds,
            )
            if stopped is not None:
                return stopped
            try:
                target = writer.ensure_target_playlist(
                    provider=stored.plan.target_provider,
                    name=stored.plan.target_playlist_name,
                    visibility=stored.plan.target_visibility,
                    idempotency_key=target_key,
                )
            except ProviderWriteError as error:
                if error.outcome is WriteOutcome.RETRYABLE:
                    checkpoint.pop("unknown_step", None)
                    return self._schedule_retry(operation, worker_id, checkpoint, now)
                if error.outcome is WriteOutcome.RATE_LIMITED:
                    checkpoint.pop("unknown_step", None)
                    return self._schedule_rate_limit(operation, worker_id, checkpoint, now, error.retry_at)
                if error.outcome is WriteOutcome.UNKNOWN_OUTCOME:
                    stopped = self._renew_or_stop(
                        operation,
                        worker_id,
                        checkpoint,
                        now,
                        lease_seconds,
                    )
                    if stopped is not None:
                        return stopped
                    try:
                        target = writer.reconcile_target_playlist(idempotency_key=target_key)
                    except Exception:
                        return self._wait_for_user(operation, worker_id, checkpoint, now)
                    if target is None:
                        return self._wait_for_user(operation, worker_id, checkpoint, now)
                else:
                    checkpoint.pop("unknown_step", None)
                    issues.append({"step": "target", "detail": error.detail, "provider_code": error.provider_code})
                    return self._finish(operation, worker_id, checkpoint | {"issues": issues}, now, "failed")
            except Exception:
                return self._wait_for_user(operation, worker_id, checkpoint, now)
            target_id = target.provider_playlist_id
            checkpoint["target_playlist_id"] = target_id
            checkpoint.pop("unknown_step", None)
            operation = self.operations.checkpoint(
                operation.operation_id,
                worker_id=worker_id,
                checkpoint=checkpoint,
                now=now,
                state="running",
            )
            if operation.state != "running":
                return operation

        for entry in writable_entries:
            if entry.occurrence_id in confirmed_ids or entry.occurrence_id in failed_steps:
                continue
            step_key = f"{digest}:entry:{entry.occurrence_id}"
            if unknown_step == entry.occurrence_id:
                stopped = self._renew_or_stop(
                    operation,
                    worker_id,
                    checkpoint,
                    now,
                    lease_seconds,
                )
                if stopped is not None:
                    return stopped
                try:
                    reconciled = writer.reconcile_entry(
                        target_playlist_id=target_id,
                        provider_track_id=entry.target_track_id or "",
                        idempotency_key=step_key,
                    )
                except Exception:
                    return self._wait_for_user(operation, worker_id, checkpoint, now)
                if not reconciled:
                    return self._wait_for_user(operation, worker_id, checkpoint, now)
                operation = self._record_confirmation(
                    operation, worker_id, checkpoint, confirmed, confirmed_ids, entry.occurrence_id, now
                )
                if operation.state != "running":
                    return operation
                unknown_step = None
                continue

            stopped = self._renew_or_stop(
                operation,
                worker_id,
                checkpoint,
                now,
                lease_seconds,
            )
            if stopped is not None:
                return stopped
            checkpoint["unknown_step"] = entry.occurrence_id
            operation = self.operations.checkpoint(
                operation.operation_id,
                worker_id=worker_id,
                checkpoint=checkpoint,
                now=now,
                state="running",
            )
            if operation.state != "running":
                return operation
            stopped = self._renew_or_stop(
                operation,
                worker_id,
                checkpoint,
                now,
                lease_seconds,
            )
            if stopped is not None:
                return stopped
            try:
                result = writer.add_entry(
                    target_playlist_id=target_id,
                    provider_track_id=entry.target_track_id or "",
                    idempotency_key=step_key,
                )
            except Exception:
                return self._wait_for_user(operation, worker_id, checkpoint, now)
            if result.outcome is WriteOutcome.UNKNOWN_OUTCOME:
                stopped = self._renew_or_stop(
                    operation,
                    worker_id,
                    checkpoint,
                    now,
                    lease_seconds,
                )
                if stopped is not None:
                    return stopped
                try:
                    reconciled = writer.reconcile_entry(
                        target_playlist_id=target_id,
                        provider_track_id=entry.target_track_id or "",
                        idempotency_key=step_key,
                    )
                except Exception:
                    return self._wait_for_user(operation, worker_id, checkpoint, now)
                if reconciled:
                    operation = self._record_confirmation(
                        operation, worker_id, checkpoint, confirmed, confirmed_ids, entry.occurrence_id, now
                    )
                    if operation.state != "running":
                        return operation
                    unknown_step = None
                    continue
                else:
                    return self._wait_for_user(operation, worker_id, checkpoint, now)
            if result.outcome is WriteOutcome.RETRYABLE:
                checkpoint.pop("unknown_step", None)
                return self._schedule_retry(operation, worker_id, checkpoint, now)
            if result.outcome is WriteOutcome.RATE_LIMITED:
                checkpoint.pop("unknown_step", None)
                return self._schedule_rate_limit(operation, worker_id, checkpoint, now, result.retry_at)
            if result.outcome is WriteOutcome.PERMANENT_FAILURE:
                checkpoint.pop("unknown_step", None)
                failed_steps.add(entry.occurrence_id)
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
                if operation.state != "running":
                    return operation
                continue
            operation = self._record_confirmation(
                operation, worker_id, checkpoint, confirmed, confirmed_ids, entry.occurrence_id, now
            )
            if operation.state != "running":
                return operation

        checkpoint["confirmed_occurrences"] = confirmed
        checkpoint["omitted_occurrences"] = [entry.occurrence_id for entry in stored.plan.omitted_entries]
        checkpoint["issues"] = issues
        terminal = "partial" if stored.plan.omitted_entries or issues else "succeeded"
        return self._finish(operation, worker_id, checkpoint, now, terminal)

    def _record_confirmation(
        self,
        operation: OperationRecord,
        worker_id: str,
        checkpoint: dict[str, Any],
        confirmed: list[str],
        confirmed_ids: set[str],
        occurrence_id: str,
        now: datetime,
    ) -> OperationRecord:
        confirmed.append(occurrence_id)
        confirmed_ids.add(occurrence_id)
        checkpoint["confirmed_occurrences"] = confirmed
        checkpoint.pop("unknown_step", None)
        return self.operations.checkpoint(
            operation.operation_id,
            worker_id=worker_id,
            checkpoint=checkpoint,
            now=now,
            state="running",
        )

    def _renew_or_stop(
        self,
        operation: OperationRecord,
        worker_id: str,
        checkpoint: dict[str, Any],
        now: datetime,
        lease_seconds: int,
    ) -> OperationRecord | None:
        try:
            self.operations.renew_lease(
                operation.operation_id,
                worker_id=worker_id,
                now=now,
                lease_seconds=lease_seconds,
            )
        except LeaseConflict:
            latest = self.operations.get(operation.operation_id)
            if (
                latest.cancel_requested
                and latest.worker_id == worker_id
                and latest.lease_expires_at is not None
                and latest.lease_expires_at > now
            ):
                return self.operations.checkpoint(
                    operation.operation_id,
                    worker_id=worker_id,
                    checkpoint=checkpoint,
                    now=now,
                    state="running",
                )
            raise
        return None

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
        retry_attempts = int(checkpoint.get("retry_attempts", 0)) + 1
        checkpoint = {**checkpoint, "retry_attempts": retry_attempts}
        if retry_attempts > self.max_retry_attempts:
            return self._finish(
                operation,
                worker_id,
                checkpoint | {"failure_code": "retry_exhausted"},
                now,
                "failed",
            )
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
