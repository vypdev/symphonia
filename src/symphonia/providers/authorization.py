"""Provider-neutral authorization-attempt values.

The raw OAuth state/code-verifier values are intentionally not represented by
the durable model. The application may hold them briefly at the boundary, but
the repository stores only a digest and exact callback binding.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AuthorizationState(str, Enum):
    CREATED = "created"
    CONSUMED = "consumed"
    DENIED = "denied"
    EXPIRED = "expired"
    FAILED = "failed"


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
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("authorization timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("authorization attempt must expire after creation")
        if self.completed_at is not None and self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware")

