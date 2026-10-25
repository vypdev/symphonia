"""Normalized provider error categories shared by adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re


_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_CREDENTIAL_NAME = (
    r"(?:token|access[_-]?token|refresh[_-]?token|id[_-]?token|"
    r"client[_-]?secret|secret|password|cookie|authorization)"
)
_ASSIGNMENT_QUOTED = re.compile(
    rf"(?i)(?P<key>[\"']?{_CREDENTIAL_NAME}[\"']?)"
    r"\s*(?P<separator>[:=])\s*"
    r"(?P<quote>[\"'])(?P<value>(?:\\.|[^\"'])*)(?P=quote)"
)
_ASSIGNMENT_UNQUOTED = re.compile(
    rf"(?i)(?P<key>[\"']?{_CREDENTIAL_NAME}[\"']?)"
    r"\s*(?P<separator>[:=])\s*"
    r"(?P<value>[^,\s;}\"'&]+)"
)


def _redact_assignment(match: re.Match[str]) -> str:
    quote = match.groupdict().get("quote") or ""
    return (
        f"{match.group('key')}{match.group('separator')}"
        f"{quote}[REDACTED]{quote}"
    )


def redact_error_detail(detail: str) -> str:
    """Remove common credential forms before an error leaves the provider port."""

    if not isinstance(detail, str) or not detail.strip():
        raise ValueError("provider error detail must not be empty")
    redacted = _BEARER.sub("Bearer [REDACTED]", detail)
    redacted = _ASSIGNMENT_QUOTED.sub(_redact_assignment, redacted)
    return _ASSIGNMENT_UNQUOTED.sub(_redact_assignment, redacted)


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
        redacted_detail = redact_error_detail(self.detail)
        object.__setattr__(self, "detail", redacted_detail)
        if self.provider_code is not None:
            object.__setattr__(self, "provider_code", redact_error_detail(self.provider_code))
        RuntimeError.__init__(self, redacted_detail)
        if not self.detail.strip():
            raise ValueError("provider error detail must not be empty")
        if self.correlation_id is not None and not self.correlation_id.strip():
            raise ValueError("correlation_id must not be blank")
