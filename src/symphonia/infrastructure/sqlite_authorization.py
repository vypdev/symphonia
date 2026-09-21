"""Durable, single-use authorization-attempt state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import sqlite3

from symphonia.providers.authorization import AuthorizationAttempt, AuthorizationState, validate_redirect_uri


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def state_digest(state: str) -> str:
    if not state or not state.strip():
        raise ValueError("authorization state must not be empty")
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


class AuthorizationAttemptNotFound(LookupError):
    pass


class AuthorizationAttemptError(ValueError):
    pass


class AuthorizationAttemptRepository:
    """Store only authorization correlation metadata, never raw state values."""

    def __init__(self, path: str = ":memory:") -> None:
        self._connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def close(self) -> None:
        self._connection.close()

    def healthcheck(self) -> bool:
        """Return whether the migrated authorization store can be read."""

        try:
            row = self._connection.execute("SELECT 1 AS healthy").fetchone()
        except sqlite3.Error:
            return False
        return row is not None and row["healthy"] == 1

    def _migrate(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS authorization_attempts (
                attempt_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                redirect_uri TEXT NOT NULL,
                state_digest TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                completed_at TEXT,
                failure_code TEXT
            );
            CREATE INDEX IF NOT EXISTS authorization_attempts_expiry_idx
                ON authorization_attempts (state, expires_at);
            """
        )

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
    ) -> AuthorizationAttempt:
        if ttl <= timedelta(0):
            raise ValueError("authorization attempt ttl must be positive")
        validate_redirect_uri(redirect_uri)
        created_at = _utc(now)
        expires_at = _utc(now + ttl)
        self._connection.execute(
            """
            INSERT INTO authorization_attempts (
                attempt_id, provider, actor_id, redirect_uri, state_digest,
                state, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, 'created', ?, ?)
            """,
            (
                attempt_id,
                provider,
                actor_id,
                redirect_uri,
                state_digest(raw_state),
                created_at,
                expires_at,
            ),
        )
        return self.get(attempt_id)

    def get(self, attempt_id: str) -> AuthorizationAttempt:
        row = self._connection.execute(
            "SELECT * FROM authorization_attempts WHERE attempt_id = ?", (attempt_id,)
        ).fetchone()
        if row is None:
            raise AuthorizationAttemptNotFound(attempt_id)
        return self._record(row)

    def consume(self, attempt_id: str, *, raw_state: str, now: datetime) -> AuthorizationAttempt:
        """Consume a matching, unexpired state exactly once."""

        now_text = _utc(now)
        digest = state_digest(raw_state)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._connection.execute(
                "SELECT * FROM authorization_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise AuthorizationAttemptNotFound(attempt_id)
            if row["state"] != AuthorizationState.CREATED.value:
                raise AuthorizationAttemptError("authorization attempt is no longer consumable")
            if row["expires_at"] <= now_text:
                self._connection.execute(
                    "UPDATE authorization_attempts SET state = 'expired', completed_at = ? WHERE attempt_id = ?",
                    (now_text, attempt_id),
                )
                self._connection.execute("COMMIT")
                raise AuthorizationAttemptError("authorization attempt has expired")
            if not hmac.compare_digest(row["state_digest"], digest):
                self._connection.execute(
                    """
                    UPDATE authorization_attempts
                       SET state = 'failed', completed_at = ?, failure_code = 'state_mismatch'
                     WHERE attempt_id = ?
                    """,
                    (now_text, attempt_id),
                )
                self._connection.execute("COMMIT")
                raise AuthorizationAttemptError("authorization state did not match")
            self._connection.execute(
                "UPDATE authorization_attempts SET state = 'consumed', completed_at = ? WHERE attempt_id = ?",
                (now_text, attempt_id),
            )
            self._connection.execute("COMMIT")
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise
        return self.get(attempt_id)

    def deny(self, attempt_id: str, *, now: datetime, failure_code: str = "consent_denied") -> AuthorizationAttempt:
        return self._complete(attempt_id, AuthorizationState.DENIED, now, failure_code)

    def expire(self, attempt_id: str, *, now: datetime) -> AuthorizationAttempt:
        return self._complete(attempt_id, AuthorizationState.EXPIRED, now, "expired")

    def _complete(
        self,
        attempt_id: str,
        state: AuthorizationState,
        now: datetime,
        failure_code: str,
    ) -> AuthorizationAttempt:
        now_text = _utc(now)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._connection.execute(
                "SELECT state FROM authorization_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise AuthorizationAttemptNotFound(attempt_id)
            if row["state"] != AuthorizationState.CREATED.value:
                raise AuthorizationAttemptError("authorization attempt is already complete")
            self._connection.execute(
                """
                UPDATE authorization_attempts
                   SET state = ?, completed_at = ?, failure_code = ?
                 WHERE attempt_id = ?
                """,
                (state.value, now_text, failure_code, attempt_id),
            )
            self._connection.execute("COMMIT")
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise
        return self.get(attempt_id)

    @staticmethod
    def _record(row: sqlite3.Row) -> AuthorizationAttempt:
        return AuthorizationAttempt(
            attempt_id=row["attempt_id"],
            provider=row["provider"],
            actor_id=row["actor_id"],
            redirect_uri=row["redirect_uri"],
            state_digest=row["state_digest"],
            state=AuthorizationState(row["state"]),
            created_at=_parse_utc(row["created_at"]),
            expires_at=_parse_utc(row["expires_at"]),
            completed_at=None if row["completed_at"] is None else _parse_utc(row["completed_at"]),
            failure_code=row["failure_code"],
        )
