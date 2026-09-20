from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from symphonia.infrastructure import (
    AuthorizationAttemptError,
    AuthorizationAttemptRepository,
    state_digest,
)
from symphonia.providers import AuthorizationState


UTC = timezone.utc
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


class AuthorizationAttemptRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = AuthorizationAttemptRepository()

    def tearDown(self) -> None:
        self.repository.close()

    def create(self, *, ttl: timedelta = timedelta(minutes=10)):
        return self.repository.create(
            attempt_id="attempt-1",
            provider="spotify",
            actor_id="ha-user-1",
            redirect_uri="https://ha.example/symphonia/callback",
            raw_state="raw-state-secret",
            now=NOW,
            ttl=ttl,
        )

    def test_persists_only_state_digest_and_exact_callback_binding(self) -> None:
        attempt = self.create()
        self.assertEqual(attempt.state, AuthorizationState.CREATED)
        self.assertEqual(attempt.state_digest, state_digest("raw-state-secret"))
        raw = self.repository._connection.execute(
            "SELECT state_digest, redirect_uri FROM authorization_attempts"
        ).fetchone()
        self.assertNotIn("raw-state-secret", str(raw))
        self.assertEqual(raw["redirect_uri"], "https://ha.example/symphonia/callback")

    def test_matching_state_is_single_use(self) -> None:
        self.create()
        consumed = self.repository.consume("attempt-1", raw_state="raw-state-secret", now=NOW + timedelta(seconds=1))
        self.assertEqual(consumed.state, AuthorizationState.CONSUMED)
        with self.assertRaises(AuthorizationAttemptError):
            self.repository.consume("attempt-1", raw_state="raw-state-secret", now=NOW + timedelta(seconds=2))

    def test_mismatch_invalidates_attempt_without_disclosing_expected_state(self) -> None:
        self.create()
        with self.assertRaises(AuthorizationAttemptError):
            self.repository.consume("attempt-1", raw_state="attacker-state", now=NOW + timedelta(seconds=1))
        failed = self.repository.get("attempt-1")
        self.assertEqual(failed.state, AuthorizationState.FAILED)
        self.assertEqual(failed.failure_code, "state_mismatch")

    def test_expired_attempt_cannot_be_consumed(self) -> None:
        self.create(ttl=timedelta(seconds=1))
        with self.assertRaises(AuthorizationAttemptError):
            self.repository.consume("attempt-1", raw_state="raw-state-secret", now=NOW + timedelta(seconds=2))
        self.assertEqual(self.repository.get("attempt-1").state, AuthorizationState.EXPIRED)

    def test_denial_is_terminal(self) -> None:
        self.create()
        denied = self.repository.deny("attempt-1", now=NOW + timedelta(seconds=1))
        self.assertEqual(denied.state, AuthorizationState.DENIED)
        with self.assertRaises(AuthorizationAttemptError):
            self.repository.expire("attempt-1", now=NOW + timedelta(seconds=2))


if __name__ == "__main__":
    unittest.main()
