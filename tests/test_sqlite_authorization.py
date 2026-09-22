from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import threading
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

    def test_healthcheck_fails_closed_on_corrupt_attempt_state(self) -> None:
        self.create()
        self.repository._connection.execute(  # type: ignore[attr-defined]
            "UPDATE authorization_attempts SET state = ? WHERE attempt_id = ?",
            ("corrupt", "attempt-1"),
        )

        self.assertFalse(self.repository.healthcheck())

    def test_callback_state_resolves_by_digest_after_repository_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "authorization.sqlite3")
            repository = AuthorizationAttemptRepository(path)
            repository.create(
                attempt_id="attempt-1",
                provider="spotify",
                actor_id="ha-user-1",
                redirect_uri="https://ha.example/symphonia/callback",
                raw_state="callback-state",
                now=NOW,
            )
            repository.close()

            restarted = AuthorizationAttemptRepository(path)
            try:
                resolved = restarted.get_by_state("callback-state")
                self.assertEqual(resolved.attempt_id, "attempt-1")
                self.assertNotEqual(resolved.state_digest, "callback-state")
            finally:
                restarted.close()

    def test_ambiguous_callback_state_fails_closed(self) -> None:
        self.create()
        self.repository.create(
            attempt_id="attempt-2",
            provider="spotify",
            actor_id="ha-user-1",
            redirect_uri="https://ha.example/symphonia/callback",
            raw_state="raw-state-secret",
            now=NOW,
        )

        with self.assertRaises(AuthorizationAttemptError):
            self.repository.get_by_state("raw-state-secret")

    def test_matching_state_is_single_use(self) -> None:
        self.create()
        consumed = self.repository.consume("attempt-1", raw_state="raw-state-secret", now=NOW + timedelta(seconds=1))
        self.assertEqual(consumed.state, AuthorizationState.CONSUMED)
        with self.assertRaises(AuthorizationAttemptError):
            self.repository.consume("attempt-1", raw_state="raw-state-secret", now=NOW + timedelta(seconds=2))

    def test_two_sqlite_connections_can_consume_a_state_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "authorization.sqlite3")
            seed = AuthorizationAttemptRepository(path)
            seed.create(
                attempt_id="attempt-1",
                provider="spotify",
                actor_id="ha-user-1",
                redirect_uri="https://ha.example/symphonia/callback",
                raw_state="raw-state-secret",
                now=NOW,
            )
            seed.close()

            start = threading.Barrier(2)
            outcomes: list[str] = []
            outcomes_lock = threading.Lock()

            def consume() -> None:
                repository = AuthorizationAttemptRepository(path)
                try:
                    start.wait(timeout=5)
                    repository.consume(
                        "attempt-1",
                        raw_state="raw-state-secret",
                        now=NOW + timedelta(seconds=1),
                    )
                    outcome = "consumed"
                except AuthorizationAttemptError:
                    outcome = "rejected"
                except Exception as error:  # pragma: no cover - keeps thread failures observable
                    outcome = f"error:{type(error).__name__}"
                finally:
                    repository.close()
                with outcomes_lock:
                    outcomes.append(outcome)

            threads = [threading.Thread(target=consume) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(sorted(outcomes), ["consumed", "rejected"])

            verifier = AuthorizationAttemptRepository(path)
            try:
                self.assertEqual(verifier.get("attempt-1").state, AuthorizationState.CONSUMED)
            finally:
                verifier.close()

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

    def test_invalid_creation_values_are_rejected_before_persistence(self) -> None:
        for field, value in (
            ("attempt_id", "   "),
            ("provider", "   "),
            ("actor_id", "   "),
            ("raw_state", "s" * 513),
        ):
            values = {
                "attempt_id": "attempt-1",
                "provider": "spotify",
                "actor_id": "ha-user-1",
                "redirect_uri": "https://ha.example/symphonia/callback",
                "raw_state": "raw-state-secret",
                "now": NOW,
            }
            values[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.repository.create(**values)
            count = self.repository._connection.execute(
                "SELECT COUNT(*) FROM authorization_attempts"
            ).fetchone()[0]
            self.assertEqual(count, 0)

    def test_failure_code_is_bounded_and_safe_for_durable_storage(self) -> None:
        self.create()
        for failure_code in ("provider detail", "TOKEN=secret", "x" * 65, ""):
            with self.subTest(failure_code=failure_code), self.assertRaises(ValueError):
                self.repository.deny(
                    "attempt-1",
                    now=NOW + timedelta(seconds=1),
                    failure_code=failure_code,
                )
            self.assertEqual(self.repository.get("attempt-1").state, AuthorizationState.CREATED)


if __name__ == "__main__":
    unittest.main()
