from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from symphonia.infrastructure import (
    ConnectionConflict,
    ConnectionNotFound,
    ProviderConnectionRepository,
)
from symphonia.providers import Capability, ConnectionState, ProviderCapabilities, ProviderConnection


UTC = timezone.utc
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def connection(*, connection_id: str = "spotify-1", account_id: str = "account-1") -> ProviderConnection:
    return ProviderConnection(
        connection_id=connection_id,
        provider="spotify",
        provider_account_id=account_id,
        state=ConnectionState.CONNECTED,
        manifest_version="spotify-2026-09",
        secret_ref="secret-ref-1",
        capabilities=ProviderCapabilities(
            enabled=frozenset({Capability.READ_PLAYLISTS}),
            evidence_version="probe-1",
            observed_at="2026-09-20T12:00:00Z",
        ),
        created_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(days=30),
        health_code=None,
    )


class ProviderConnectionRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = ProviderConnectionRepository()

    def tearDown(self) -> None:
        self.repository.close()

    def test_create_round_trips_capabilities_and_only_persists_secret_reference(self) -> None:
        stored = self.repository.create(connection())
        self.assertEqual(stored, connection())
        self.assertEqual(stored.capabilities.enabled, frozenset({Capability.READ_PLAYLISTS}))
        raw = self.repository._connection.execute(
            "SELECT secret_ref, capabilities_json FROM provider_connections"
        ).fetchone()
        self.assertEqual(raw["secret_ref"], "secret-ref-1")
        self.assertNotIn("access-token", str(raw))

    def test_same_connection_is_idempotent_but_account_collision_is_rejected(self) -> None:
        first = connection()
        self.repository.create(first)
        self.assertEqual(self.repository.create(first), first)
        with self.assertRaises(ConnectionConflict):
            self.repository.create(connection(connection_id="spotify-2"))

    def test_probe_updates_health_and_capabilities(self) -> None:
        self.repository.create(connection())
        degraded = self.repository.record_probe(
            "spotify-1",
            state=ConnectionState.DEGRADED,
            capabilities=ProviderCapabilities(
                enabled=frozenset(),
                evidence_version="probe-2",
                observed_at="2026-09-20T12:01:00Z",
            ),
            health_code="provider_unavailable",
            expires_at=NOW + timedelta(days=29),
            now=NOW + timedelta(minutes=1),
        )
        self.assertEqual(degraded.state, ConnectionState.DEGRADED)
        self.assertEqual(degraded.health_code, "provider_unavailable")
        self.assertEqual(degraded.capabilities.enabled, frozenset())

    def test_disconnect_erases_local_secret_reference_and_capabilities(self) -> None:
        self.repository.create(connection())
        disconnected = self.repository.disconnect("spotify-1", now=NOW + timedelta(minutes=2))
        self.assertEqual(disconnected.state, ConnectionState.DISCONNECTED)
        self.assertIsNone(disconnected.secret_ref)
        self.assertIsNone(disconnected.capabilities)
        self.assertEqual(self.repository.list(provider="spotify")[0].health_code, "disconnected")

    def test_health_summary_contains_only_provider_state_counts(self) -> None:
        self.repository.create(connection())
        self.repository.create(
            ProviderConnection(
                connection_id="spotify-2",
                provider="spotify",
                provider_account_id="account-2",
                state=ConnectionState.ACTION_REQUIRED,
                manifest_version="v1",
                secret_ref="opaque-secret-2",
                capabilities=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )

        summary = self.repository.health_summary()

        self.assertEqual(summary, {"total": 2, "by_provider": {"spotify": {"action_required": 1, "connected": 1}}})
        self.assertNotIn("account-1", str(summary))
        self.assertNotIn("opaque-secret", str(summary))

    def test_missing_connection_is_explicit(self) -> None:
        with self.assertRaises(ConnectionNotFound):
            self.repository.get("missing")

    def test_disconnected_model_rejects_a_secret_reference(self) -> None:
        with self.assertRaises(ValueError):
            ProviderConnection(
                connection_id="spotify-disconnected",
                provider="spotify",
                provider_account_id="account-1",
                state=ConnectionState.DISCONNECTED,
                manifest_version="spotify-2026-09",
                secret_ref="must-not-remain",
                capabilities=None,
                created_at=NOW,
                updated_at=NOW,
            )


if __name__ == "__main__":
    unittest.main()
