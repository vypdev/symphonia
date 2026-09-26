from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.application import AuthorizationService
from symphonia.infrastructure import AuthorizationAttemptRepository
from symphonia.providers import AuthorizationState


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


class AuthorizationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = AuthorizationAttemptRepository()
        self.service = AuthorizationService(
            self.repository,
            state_factory=lambda: "raw-state-only-at-boundary",
            id_factory=lambda: "attempt-1",
        )

    def tearDown(self) -> None:
        self.repository.close()

    def test_begin_returns_raw_state_but_repository_has_only_digest(self) -> None:
        started = self.service.begin(
            provider="spotify",
            actor_id="ha-user-1",
            redirect_uri="https://ha.example/symphonia/callback",
            now=NOW,
        )
        self.assertEqual(started.raw_state, "raw-state-only-at-boundary")
        self.assertEqual(started.attempt.state, AuthorizationState.CREATED)
        stored = self.repository.get("attempt-1")
        self.assertNotEqual(stored.state_digest, started.raw_state)
        raw = self.repository._connection.execute(
            "SELECT state_digest FROM authorization_attempts WHERE attempt_id = 'attempt-1'"
        ).fetchone()[0]
        self.assertNotIn(started.raw_state, raw)

    def test_consume_and_deny_delegate_single_use_transitions(self) -> None:
        self.service.begin(
            provider="spotify",
            actor_id="ha-user-1",
            redirect_uri="https://ha.example/symphonia/callback",
            now=NOW,
        )
        consumed = self.service.consume("attempt-1", raw_state="raw-state-only-at-boundary", now=NOW)
        self.assertEqual(consumed.state, AuthorizationState.CONSUMED)

        self.service = AuthorizationService(
            self.repository,
            state_factory=lambda: "another-state",
            id_factory=lambda: "attempt-2",
        )
        self.service.begin(
            provider="spotify",
            actor_id="ha-user-1",
            redirect_uri="https://ha.example/symphonia/callback",
            now=NOW,
        )
        denied = self.service.deny("attempt-2", now=NOW)
        self.assertEqual(denied.state, AuthorizationState.DENIED)

    def test_callback_consumption_resolves_the_durable_attempt_by_state(self) -> None:
        self.service.begin(
            provider="spotify",
            actor_id="ha-user-1",
            redirect_uri="https://ha.example/symphonia/callback",
            now=NOW,
        )

        consumed = self.service.consume_callback(raw_state="raw-state-only-at-boundary", now=NOW)

        self.assertEqual(consumed.attempt_id, "attempt-1")
        self.assertEqual(consumed.state, AuthorizationState.CONSUMED)

    def test_callback_provider_binding_is_checked_before_consumption(self) -> None:
        self.service.begin(
            provider="spotify",
            actor_id="ha-user-1",
            redirect_uri="https://ha.example/symphonia/callback",
            now=NOW,
        )

        with self.assertRaises(ValueError):
            self.service.consume_callback_for_provider(
                raw_state="raw-state-only-at-boundary",
                provider="google",
                now=NOW,
            )

        self.assertEqual(self.repository.get("attempt-1").state, AuthorizationState.CREATED)

    def test_redirect_uri_rejects_unsafe_callback_forms(self) -> None:
        for redirect_uri in (
            "javascript:alert(1)",
            "https://ha.example/callback#fragment",
            "https://user:password@ha.example/callback",
            "http://remote.example/callback",
        ):
            with self.subTest(redirect_uri=redirect_uri), self.assertRaises(ValueError):
                self.service.begin(
                    provider="spotify",
                    actor_id="ha-user-1",
                    redirect_uri=redirect_uri,
                    now=NOW,
                )

        with self.assertRaises(ValueError):
            self.service.begin(
                provider="spotify",
                actor_id="ha-user-1",
                redirect_uri=None,  # type: ignore[arg-type]
                now=NOW,
            )


if __name__ == "__main__":
    unittest.main()
