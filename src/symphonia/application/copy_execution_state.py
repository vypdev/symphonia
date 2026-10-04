"""Mutable state shared by one claimed copy execution and its write stages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from symphonia.domain.operations import LeaseConflict, OperationRecord
from symphonia.domain.plans import CopyPlanRecord
from symphonia.providers.writing import PlaylistWriter

from .copy_checkpoint import CopyProgress
from .ports import OperationPort


@dataclass(slots=True)
class CopyRun:
    operations: OperationPort
    writer: PlaylistWriter
    stored: CopyPlanRecord
    operation: OperationRecord
    worker_id: str
    now: datetime
    lease_seconds: int
    retry_delay_seconds: int
    max_retry_attempts: int
    checkpoint: dict[str, Any]
    progress: CopyProgress

    def checkpoint_running(self) -> OperationRecord:
        self.operation = self.operations.checkpoint(
            self.operation.operation_id,
            worker_id=self.worker_id,
            checkpoint=self.checkpoint,
            now=self.now,
            state="running",
        )
        return self.operation

    def confirm(self, occurrence_id: str) -> OperationRecord:
        self.progress.confirmed.append(occurrence_id)
        self.progress.confirmed_ids.add(occurrence_id)
        self.checkpoint["confirmed_occurrences"] = self.progress.confirmed
        self.checkpoint.pop("unknown_step", None)
        self.progress.unknown_step = None
        return self.checkpoint_running()

    def renew_or_stop(self) -> OperationRecord | None:
        try:
            self.operations.renew_lease(
                self.operation.operation_id,
                worker_id=self.worker_id,
                now=self.now,
                lease_seconds=self.lease_seconds,
            )
        except LeaseConflict:
            latest = self.operations.get(self.operation.operation_id)
            if (
                latest.cancel_requested
                and latest.worker_id == self.worker_id
                and latest.lease_expires_at is not None
                and latest.lease_expires_at > self.now
            ):
                return self.checkpoint_running()
            raise
        return None

    def finish(self, state: str, *, checkpoint: dict[str, Any] | None = None) -> OperationRecord:
        return self.operations.checkpoint(
            self.operation.operation_id,
            worker_id=self.worker_id,
            checkpoint=self.checkpoint if checkpoint is None else checkpoint,
            now=self.now,
            state=state,
        )

    def wait_for_user(self) -> OperationRecord:
        return self.finish("waiting_user")

    def schedule_retry(self) -> OperationRecord:
        retry_attempts = int(self.checkpoint.get("retry_attempts", 0)) + 1
        self.checkpoint = {**self.checkpoint, "retry_attempts": retry_attempts}
        if retry_attempts > self.max_retry_attempts:
            return self.finish(
                "failed", checkpoint=self.checkpoint | {"failure_code": "retry_exhausted"}
            )
        return self.operations.schedule_retry(
            self.operation.operation_id,
            worker_id=self.worker_id,
            next_run_at=self.now + timedelta(seconds=self.retry_delay_seconds),
            checkpoint=self.checkpoint,
            now=self.now,
        )

    def schedule_rate_limit(self, retry_at: datetime | None) -> OperationRecord:
        next_run_at = (
            retry_at if retry_at is not None and retry_at > self.now
            else self.now + timedelta(seconds=self.retry_delay_seconds)
        )
        return self.operations.schedule_rate_limit(
            self.operation.operation_id,
            worker_id=self.worker_id,
            next_run_at=next_run_at,
            checkpoint=self.checkpoint,
            now=self.now,
        )
