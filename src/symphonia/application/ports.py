"""Storage contracts owned by the application use cases.

Concrete repositories satisfy these protocols structurally at composition time.
The contracts carry provider-neutral values and never expose SQLite details.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Protocol

from symphonia.domain.models import CopyPlan
from symphonia.domain.operations import OperationRecord
from symphonia.domain.plans import CopyPlanRecord
from symphonia.domain.projections import PublishedPlaylistSnapshot
from symphonia.providers.authorization import AuthorizationAttempt
from symphonia.providers.connections import ConnectionState, ProviderConnection
from symphonia.providers.contracts import ProviderCapabilities
from symphonia.providers.importing import CollectionImportResult


class AuthorizationAttemptPort(Protocol):
    def create(
        self,
        *,
        attempt_id: str,
        provider: str,
        actor_id: str,
        redirect_uri: str,
        raw_state: str,
        now: datetime,
        ttl: timedelta = timedelta(minutes=10),
    ) -> AuthorizationAttempt: ...

    def get_by_state(self, raw_state: str) -> AuthorizationAttempt: ...

    def consume(self, attempt_id: str, *, raw_state: str, now: datetime) -> AuthorizationAttempt: ...

    def deny(
        self,
        attempt_id: str,
        *,
        now: datetime,
        failure_code: str = "consent_denied",
    ) -> AuthorizationAttempt: ...


class ProviderConnectionPort(Protocol):
    def create(self, connection: ProviderConnection) -> ProviderConnection: ...

    def get(self, connection_id: str) -> ProviderConnection: ...

    def record_probe(
        self,
        connection_id: str,
        *,
        state: ConnectionState,
        capabilities: ProviderCapabilities | None,
        health_code: str | None,
        expires_at: datetime | None,
        now: datetime,
    ) -> ProviderConnection: ...

    def disconnect(self, connection_id: str, *, now: datetime) -> ProviderConnection: ...


class PlaylistProjectionPort(Protocol):
    def publish(
        self,
        result: CollectionImportResult,
        *,
        snapshot_id: str,
        published_at: datetime,
    ) -> PublishedPlaylistSnapshot: ...

    def current(
        self,
        *,
        provider: str,
        namespace: str,
        playlist_id: str,
    ) -> PublishedPlaylistSnapshot | None: ...


class CopyPlanPort(Protocol):
    def save(self, plan: CopyPlan, *, now: datetime) -> CopyPlanRecord: ...

    def get(self, digest: str) -> CopyPlanRecord: ...

    def accept(self, digest: str, *, expected_digest: str, now: datetime) -> CopyPlanRecord: ...


class OperationPort(Protocol):
    """The durable operations needed by current application use cases."""

    def create(
        self,
        *,
        operation_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
        now: datetime,
        operation_id: str | None = None,
    ) -> OperationRecord: ...

    def get(self, operation_id: str) -> OperationRecord: ...

    def claim(
        self, operation_id: str, *, worker_id: str, now: datetime,
        lease_seconds: int = 30,
    ) -> OperationRecord: ...

    def claim_next(
        self, *, worker_id: str, now: datetime, lease_seconds: int = 30,
        operation_type: str | None = None,
    ) -> OperationRecord | None: ...

    def renew_lease(
        self, operation_id: str, *, worker_id: str, now: datetime,
        lease_seconds: int = 30,
    ) -> OperationRecord: ...

    def checkpoint(
        self, operation_id: str, *, worker_id: str, checkpoint: dict[str, Any],
        now: datetime, state: str = "running",
    ) -> OperationRecord: ...

    def schedule_retry(
        self, operation_id: str, *, worker_id: str, next_run_at: datetime,
        checkpoint: dict[str, Any], now: datetime,
    ) -> OperationRecord: ...

    def schedule_rate_limit(
        self, operation_id: str, *, worker_id: str, next_run_at: datetime,
        checkpoint: dict[str, Any], now: datetime,
    ) -> OperationRecord: ...
