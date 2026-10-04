"""Durable operation orchestration for playlist imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from symphonia.domain.operations import LeaseConflict, OperationRecord
from symphonia.providers.contracts import ProviderAdapter, ProviderObjectRef
from symphonia.providers.errors import ProviderApiError

from .library_import import LibraryImportService
from .library_import_execution_state import ImportRun
from .library_import_payload import parse_import_payload
from .ports import OperationPort


@dataclass(frozen=True, slots=True)
class LibraryImportExecutionService:
    """Make import publication resumable and visible as a durable operation."""

    imports: LibraryImportService
    operations: OperationPort
    retry_delay_seconds: int = 60
    max_retry_attempts: int = 5

    def __post_init__(self) -> None:
        if self.retry_delay_seconds <= 0:
            raise ValueError("retry_delay_seconds must be positive")
        if self.max_retry_attempts < 0:
            raise ValueError("max_retry_attempts must not be negative")

    def enqueue_playlist(
        self,
        adapter: ProviderAdapter,
        *,
        connection_id: str,
        playlist: ProviderObjectRef,
        snapshot_id: str,
        observed_at: datetime,
        now: datetime,
    ) -> OperationRecord:
        """Persist import intent before the first provider read."""

        if adapter.manifest.provider != playlist.provider:
            raise ValueError("adapter provider does not match playlist provider")
        if observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        payload = {
            "provider": playlist.provider,
            "connection_id": connection_id,
            "playlist": {
                "provider": playlist.provider,
                "object_type": playlist.object_type,
                "object_id": playlist.object_id,
                "namespace": playlist.namespace,
            },
            "snapshot_id": snapshot_id,
            "observed_at": observed_at.astimezone(timezone.utc).isoformat(timespec="microseconds"),
        }
        idempotency_key = (
            f"import:{connection_id}:{playlist.object_type}:{playlist.object_id}:{snapshot_id}"
        )
        return self.operations.create(
            operation_type="import_playlist",
            idempotency_key=idempotency_key,
            payload=payload,
            now=now,
        )

    def execute_claimed(
        self,
        operation: OperationRecord,
        *,
        adapter: ProviderAdapter,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 30,
    ) -> OperationRecord:
        """Run one claimed import and turn provider failures into safe states."""

        if operation.state != "running" or operation.worker_id != worker_id:
            raise ValueError("import operation must be running under the supplied worker")
        run = ImportRun(
            self.operations, operation, worker_id, now, dict(operation.checkpoint),
            self.retry_delay_seconds, self.max_retry_attempts,
        )
        if operation.cancel_requested:
            return run.checkpoint_state("cancelled")
        retry_attempts = run.checkpoint.get("retry_attempts", 0)
        if type(retry_attempts) is not int or retry_attempts < 0:
            run.checkpoint["failure_code"] = "invalid_retry_checkpoint"
            return run.checkpoint_state("failed")
        try:
            connection_id, playlist, snapshot_id, observed_at = parse_import_payload(
                operation.payload
            )
            if adapter.manifest.provider != playlist.provider:
                raise ValueError("adapter provider does not match operation playlist")
            self.operations.renew_lease(
                operation.operation_id,
                worker_id=worker_id,
                now=now,
                lease_seconds=lease_seconds,
            )
            publication = self.imports.import_playlist(
                adapter,
                connection_id=connection_id,
                playlist=playlist,
                snapshot_id=snapshot_id,
                observed_at=observed_at,
            )
        except LeaseConflict:
            cancelled = run.cancel_if_requested()
            if cancelled is not None:
                return cancelled
            raise
        except ProviderApiError as error:
            return run.handle_provider_error(error)
        except Exception as error:
            return run.fail_unexpected(error)

        return run.complete(publication)

__all__ = ["LibraryImportExecutionService"]
