"""Application use cases for verified provider connections and probes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from symphonia.infrastructure.sqlite_connections import ProviderConnectionRepository
from symphonia.providers.connections import ConnectionState, ProviderConnection
from symphonia.providers.errors import ProviderApiError, ProviderErrorCategory
from symphonia.providers.registry import ProviderRegistry


@dataclass(frozen=True, slots=True)
class ProviderConnectionService:
    connections: ProviderConnectionRepository
    providers: ProviderRegistry

    def register_verified(
        self,
        *,
        connection_id: str,
        provider: str,
        provider_account_id: str,
        manifest_version: str,
        secret_ref: str,
        now: datetime,
    ) -> ProviderConnection:
        """Persist an already verified account without accepting token material."""

        adapter = self.providers.get(provider)
        if not adapter.manifest.provider == provider:
            raise ValueError("provider manifest mismatch")
        return self.connections.create(
            ProviderConnection(
                connection_id=connection_id,
                provider=provider,
                provider_account_id=provider_account_id,
                state=ConnectionState.CONNECTED,
                manifest_version=manifest_version,
                secret_ref=secret_ref,
                capabilities=None,
                created_at=now,
                updated_at=now,
            )
        )

    def probe(self, connection_id: str, *, now: datetime) -> ProviderConnection:
        current = self.connections.get(connection_id)
        adapter = self.providers.get(current.provider)
        try:
            capabilities = adapter.capabilities(connection_id)
        except ProviderApiError as error:
            state = (
                ConnectionState.ACTION_REQUIRED
                if error.category in {
                    ProviderErrorCategory.AUTHENTICATION_REQUIRED,
                    ProviderErrorCategory.AUTHORIZATION_REVOKED,
                    ProviderErrorCategory.PERMISSION_DENIED,
                }
                else ConnectionState.DEGRADED
            )
            return self.connections.record_probe(
                connection_id,
                state=state,
                capabilities=None,
                health_code=error.category.value,
                expires_at=current.expires_at,
                now=now,
            )
        return self.connections.record_probe(
            connection_id,
            state=ConnectionState.CONNECTED,
            capabilities=capabilities,
            health_code=None,
            expires_at=current.expires_at,
            now=now,
        )

    def disconnect(self, connection_id: str, *, now: datetime) -> ProviderConnection:
        return self.connections.disconnect(connection_id, now=now)

