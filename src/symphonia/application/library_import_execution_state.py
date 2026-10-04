"""Durable outcomes for one claimed playlist-import attempt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from symphonia.domain.operations import OperationRecord
from symphonia.providers.errors import ProviderApiError, ProviderErrorCategory

from .library_import import ImportPublication
from .ports import OperationPort


@dataclass(slots=True)
class ImportRun:
    operations: OperationPort
    operation: OperationRecord
    worker_id: str
    now: datetime
    checkpoint: dict[str, Any]
    retry_delay_seconds: int
    max_retry_attempts: int

    def cancel_if_requested(self) -> OperationRecord | None:
        """A lease renewal can lose a cancellation race before the first read."""

        latest = self.operations.get(self.operation.operation_id)
        if (
            latest.cancel_requested
            and latest.worker_id == self.worker_id
            and latest.lease_expires_at is not None
            and latest.lease_expires_at > self.now
        ):
            return self.checkpoint_state("cancelled", operation=latest)
        return None

    def checkpoint_state(
        self, state: str, *, operation: OperationRecord | None = None,
    ) -> OperationRecord:
        current = self.operation if operation is None else operation
        return self.operations.checkpoint(
            current.operation_id,
            worker_id=self.worker_id,
            checkpoint=self.checkpoint,
            now=self.now,
            state=state,
        )

    def complete(self, publication: ImportPublication) -> OperationRecord:
        self.checkpoint.update(
            {
                "publication_state": publication.state,
                "issues": [issue.value for issue in publication.issues],
                "published_snapshot_id": None
                if publication.snapshot is None else publication.snapshot.snapshot_id,
                "retained_snapshot_id": None
                if publication.retained_current is None
                else publication.retained_current.snapshot_id,
            }
        )
        return self.checkpoint_state(publication.state)

    def fail_unexpected(self, error: Exception) -> OperationRecord:
        self.checkpoint["failure_code"] = f"import_exception:{type(error).__name__}"
        return self.checkpoint_state("failed")

    def handle_provider_error(self, error: ProviderApiError) -> OperationRecord:
        self.checkpoint["failure_code"] = error.category.value
        if error.category in {
            ProviderErrorCategory.AUTHENTICATION_REQUIRED,
            ProviderErrorCategory.AUTHORIZATION_REVOKED,
            ProviderErrorCategory.PERMISSION_DENIED,
        }:
            return self.checkpoint_state("waiting_user")
        if error.category is ProviderErrorCategory.RATE_LIMITED:
            retry_at = (
                error.retry_at if error.retry_at and error.retry_at > self.now
                else self.now + timedelta(seconds=self.retry_delay_seconds)
            )
            return self.operations.schedule_rate_limit(
                self.operation.operation_id,
                worker_id=self.worker_id,
                next_run_at=retry_at,
                checkpoint=self.checkpoint,
                now=self.now,
            )
        if error.category in {
            ProviderErrorCategory.PROVIDER_UNAVAILABLE,
            ProviderErrorCategory.TIMEOUT,
            ProviderErrorCategory.NETWORK_ERROR,
        }:
            retry_attempts = int(self.checkpoint.get("retry_attempts", 0)) + 1
            self.checkpoint["retry_attempts"] = retry_attempts
            if retry_attempts > self.max_retry_attempts:
                self.checkpoint["failure_code"] = "retry_exhausted"
                return self.checkpoint_state("failed")
            return self.operations.schedule_retry(
                self.operation.operation_id,
                worker_id=self.worker_id,
                next_run_at=self.now + timedelta(seconds=self.retry_delay_seconds),
                checkpoint=self.checkpoint,
                now=self.now,
            )
        return self.checkpoint_state("failed")
