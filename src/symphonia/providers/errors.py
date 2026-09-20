"""Normalized provider error categories shared by adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ProviderErrorCategory(str, Enum):
    AUTHENTICATION_REQUIRED = "authentication_required"
    AUTHORIZATION_REVOKED = "authorization_revoked"
    PERMISSION_DENIED = "permission_denied"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    NOT_FOUND = "not_found"
    ITEM_UNAVAILABLE = "item_unavailable"
    INVALID_REQUEST = "invalid_request"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    CONFLICT = "conflict"
    UNKNOWN_WRITE_OUTCOME = "unknown_write_outcome"
    PROVIDER_CONTRACT_CHANGED = "provider_contract_changed"


@dataclass(frozen=True, slots=True)
class ProviderApiError(RuntimeError):
    category: ProviderErrorCategory
    detail: str
    provider_code: str | None = None
    retry_at: datetime | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.detail)
        if not self.detail.strip():
            raise ValueError("provider error detail must not be empty")
        if self.correlation_id is not None and not self.correlation_id.strip():
            raise ValueError("correlation_id must not be blank")

