"""Application orchestration for provider-neutral authorization attempts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import secrets
import uuid
from typing import Callable

from symphonia.infrastructure.sqlite_authorization import AuthorizationAttemptRepository
from symphonia.providers.authorization import AuthorizationAttempt, validate_redirect_uri


@dataclass(frozen=True, slots=True)
class AuthorizationStart:
    """Boundary result; ``raw_state`` must not enter logs or persistence."""

    attempt: AuthorizationAttempt
    raw_state: str


@dataclass(frozen=True, slots=True)
class AuthorizationService:
    attempts: AuthorizationAttemptRepository
    state_factory: Callable[[], str] = secrets.token_urlsafe
    id_factory: Callable[[], str] = lambda: str(uuid.uuid4())

    def begin(
        self,
        *,
        provider: str,
        actor_id: str,
        redirect_uri: str,
        now: datetime,
        ttl: timedelta = timedelta(minutes=10),
    ) -> AuthorizationStart:
        validate_redirect_uri(redirect_uri)
        raw_state = self.state_factory()
        attempt = self.attempts.create(
            attempt_id=self.id_factory(),
            provider=provider,
            actor_id=actor_id,
            redirect_uri=redirect_uri,
            raw_state=raw_state,
            now=now,
            ttl=ttl,
        )
        return AuthorizationStart(attempt=attempt, raw_state=raw_state)

    def consume(self, attempt_id: str, *, raw_state: str, now: datetime) -> AuthorizationAttempt:
        return self.attempts.consume(attempt_id, raw_state=raw_state, now=now)

    def deny(self, attempt_id: str, *, now: datetime, failure_code: str = "consent_denied") -> AuthorizationAttempt:
        return self.attempts.deny(attempt_id, now=now, failure_code=failure_code)
