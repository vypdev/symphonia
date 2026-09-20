"""Provider-neutral authorization-attempt values.

The raw OAuth state/code-verifier values are intentionally not represented by
the durable model. The application may hold them briefly at the boundary, but
the repository stores only a digest and exact callback binding.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from urllib.parse import urlsplit


class AuthorizationState(str, Enum):
    CREATED = "created"
    CONSUMED = "consumed"
    DENIED = "denied"
    EXPIRED = "expired"
    FAILED = "failed"


def validate_redirect_uri(value: str) -> str:
    """Validate a fixed OAuth callback URI before durable binding."""

    if not value or not value.strip() or any(character.isspace() for character in value):
        raise ValueError("redirect_uri must be a nonblank URI without whitespace")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("redirect_uri must use http(s) and include a host")
    if parsed.fragment:
        raise ValueError("redirect_uri must not include a fragment")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("redirect_uri must not embed credentials")
    if parsed.scheme == "http" and parsed.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("http redirect_uri is only allowed for loopback hosts")
    return value


@dataclass(frozen=True, slots=True)
class AuthorizationAttempt:
    attempt_id: str
    provider: str
    actor_id: str
    redirect_uri: str
    state_digest: str
    state: AuthorizationState
    created_at: datetime
    expires_at: datetime
    completed_at: datetime | None = None
    failure_code: str | None = None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.attempt_id, "attempt_id"),
            (self.provider, "provider"),
            (self.actor_id, "actor_id"),
            (self.redirect_uri, "redirect_uri"),
            (self.state_digest, "state_digest"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        validate_redirect_uri(self.redirect_uri)
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("authorization timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("authorization attempt must expire after creation")
        if self.completed_at is not None and self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware")
