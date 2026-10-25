"""Provider connection values shared by application and infrastructure ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .contracts import ProviderCapabilities


class ConnectionState(str, Enum):
    """Durable health/action states for a verified provider account."""

    CONNECTED = "connected"
    DEGRADED = "degraded"
    ACTION_REQUIRED = "action_required"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True)
class ProviderConnection:
    """A verified provider account with only an opaque secret reference."""

    connection_id: str
    provider: str
    provider_account_id: str
    state: ConnectionState
    manifest_version: str
    secret_ref: str | None
    capabilities: ProviderCapabilities | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    health_code: str | None = None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.connection_id, "connection_id"),
            (self.provider, "provider"),
            (self.provider_account_id, "provider_account_id"),
            (self.manifest_version, "manifest_version"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.state is not ConnectionState.DISCONNECTED and not self.secret_ref:
            raise ValueError("active connections require an opaque secret_ref")
        if self.state is ConnectionState.DISCONNECTED and self.secret_ref is not None:
            raise ValueError("disconnected connections must not retain a secret_ref")
        if self.secret_ref is not None and not self.secret_ref.strip():
            raise ValueError("secret_ref must not be blank")
        for value, field_name in ((self.created_at, "created_at"), (self.updated_at, "updated_at")):
            if value.tzinfo is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
