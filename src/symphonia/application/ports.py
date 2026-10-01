"""Storage contracts owned by the application use cases.

Concrete repositories satisfy these protocols structurally at composition time.
The contracts carry provider-neutral values and never expose SQLite details.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from symphonia.providers.authorization import AuthorizationAttempt
from symphonia.providers.connections import ConnectionState, ProviderConnection
from symphonia.providers.contracts import ProviderCapabilities


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
