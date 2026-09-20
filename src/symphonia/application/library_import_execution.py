"""Durable operation orchestration for playlist imports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from symphonia.infrastructure.sqlite_operations import OperationRecord, OperationRepository
from symphonia.providers.contracts import ProviderAdapter, ProviderObjectRef
from symphonia.providers.errors import ProviderApiError, ProviderErrorCategory

from .library_import import ImportPublication, LibraryImportService


@dataclass(frozen=True, slots=True)
class LibraryImportExecutionService:
    """Make import publication resumable and visible as a durable operation."""

    imports: LibraryImportService
    operations: OperationRepository
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
        checkpoint = dict(operation.checkpoint)
        if operation.cancel_requested:
            return self._checkpoint(operation, worker_id, checkpoint, now, "cancelled")
        try:
            connection_id, playlist, snapshot_id, observed_at = self._payload(operation.payload)
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
        except ProviderApiError as error:
            checkpoint["failure_code"] = error.category.value
            if error.category in {
                ProviderErrorCategory.AUTHENTICATION_REQUIRED,
                ProviderErrorCategory.AUTHORIZATION_REVOKED,
                ProviderErrorCategory.PERMISSION_DENIED,
            }:
                return self._checkpoint(operation, worker_id, checkpoint, now, "waiting_user")
            if error.category is ProviderErrorCategory.RATE_LIMITED:
                retry_at = error.retry_at if error.retry_at and error.retry_at > now else now + timedelta(seconds=self.retry_delay_seconds)
                return self.operations.schedule_rate_limit(
                    operation.operation_id,
                    worker_id=worker_id,
                    next_run_at=retry_at,
                    checkpoint=checkpoint,
                    now=now,
                )
            if error.category in {
                ProviderErrorCategory.PROVIDER_UNAVAILABLE,
                ProviderErrorCategory.TIMEOUT,
                ProviderErrorCategory.NETWORK_ERROR,
            }:
                retry_attempts = int(checkpoint.get("retry_attempts", 0)) + 1
                checkpoint["retry_attempts"] = retry_attempts
                if retry_attempts > self.max_retry_attempts:
                    checkpoint["failure_code"] = "retry_exhausted"
                    return self._checkpoint(operation, worker_id, checkpoint, now, "failed")
                return self.operations.schedule_retry(
                    operation.operation_id,
                    worker_id=worker_id,
                    next_run_at=now + timedelta(seconds=self.retry_delay_seconds),
                    checkpoint=checkpoint,
                    now=now,
                )
            return self._checkpoint(operation, worker_id, checkpoint, now, "failed")
        except Exception as error:
            checkpoint["failure_code"] = f"import_exception:{type(error).__name__}"
            return self._checkpoint(operation, worker_id, checkpoint, now, "failed")

        return self._complete_publication(operation, worker_id, publication, checkpoint, now)

    def _complete_publication(
        self,
        operation: OperationRecord,
        worker_id: str,
        publication: ImportPublication,
        checkpoint: dict[str, Any],
        now: datetime,
    ) -> OperationRecord:
        checkpoint.update(
            {
                "publication_state": publication.state,
                "issues": [issue.value for issue in publication.issues],
                "published_snapshot_id": None if publication.snapshot is None else publication.snapshot.snapshot_id,
                "retained_snapshot_id": None
                if publication.retained_current is None
                else publication.retained_current.snapshot_id,
            }
        )
        return self._checkpoint(operation, worker_id, checkpoint, now, publication.state)

    def _checkpoint(
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

    @staticmethod
    def _payload(payload: Mapping[str, Any]) -> tuple[str, ProviderObjectRef, str, datetime]:
        connection_id = payload.get("connection_id")
        snapshot_id = payload.get("snapshot_id")
        observed_at = payload.get("observed_at")
        raw_playlist = payload.get("playlist")
        if not all(isinstance(value, str) and value.strip() for value in (connection_id, snapshot_id, observed_at)):
            raise ValueError("import operation payload is missing required fields")
        if not isinstance(raw_playlist, Mapping):
            raise ValueError("import operation payload has no playlist reference")
        try:
            playlist = ProviderObjectRef(
                str(raw_playlist["provider"]),
                str(raw_playlist["object_type"]),
                str(raw_playlist["object_id"]),
                str(raw_playlist["namespace"]),
            )
            parsed_observed_at = datetime.fromisoformat(observed_at)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("import operation payload has an invalid playlist or timestamp") from error
        if parsed_observed_at.tzinfo is None:
            raise ValueError("import operation observed_at must be timezone-aware")
        return connection_id, playlist, snapshot_id, parsed_observed_at.astimezone(timezone.utc)


__all__ = ["LibraryImportExecutionService"]
