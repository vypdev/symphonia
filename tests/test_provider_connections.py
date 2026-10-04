from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.application import ProviderConnectionService
from symphonia.infrastructure import ProviderConnectionRepository
from symphonia.providers import (
    AccessBasis,
    Capability,
    ProviderApiError,
    ProviderCapabilities,
    ProviderErrorCategory,
    ProviderManifest,
    ProviderRegistry,
    redact_error_detail,
)


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


class FakeAdapter:
    def __init__(self, error: ProviderApiError | None = None) -> None:
        self.manifest = ProviderManifest("spotify", "Spotify", AccessBasis.OFFICIAL, "beta", "fixture")
        self.error = error

    def capabilities(self, connection_id: str) -> ProviderCapabilities:
        if self.error is not None:
            raise self.error
        return ProviderCapabilities(
            enabled=frozenset({Capability.READ_PLAYLISTS}),
            evidence_version="fixture-1",
            observed_at="2026-09-20T12:00:00Z",
        )

    def read_playlist_pages(self, connection_id, playlist, cursor=None):
        return ()


class ProviderConnectionServiceTests(unittest.TestCase):
    def test_provider_error_detail_redacts_common_credentials(self) -> None:
        detail = redact_error_detail(
            'Bearer abc123 token=secret refresh_token="refresh-value" '
            'json={"access_token":"json-secret","client_secret": "client-value"} '
            "cookie='cookie-value' password=\"two words\" authorization: 'header secret'"
        )
        error = ProviderApiError(
            ProviderErrorCategory.NETWORK_ERROR,
            detail,
            provider_code="authorization=header-secret",
        )

        self.assertNotIn("abc123", str(error))
        self.assertNotIn("refresh-value", str(error))
        self.assertNotIn("json-secret", str(error))
        self.assertNotIn("client-value", str(error))
        self.assertNotIn("cookie-value", str(error))
        self.assertNotIn("two words", str(error))
        self.assertNotIn("header secret", str(error))
        self.assertIn('access_token":"[REDACTED]"', str(error))
        self.assertIn('client_secret":"[REDACTED]"', str(error))
        self.assertIn("cookie='[REDACTED]'", str(error))
        self.assertEqual(error.provider_code, "authorization=[REDACTED]")
        self.assertNotIn("header-secret", error.provider_code)

    def setUp(self) -> None:
        self.connections = ProviderConnectionRepository()
        self.registry = ProviderRegistry()
        self.adapter = FakeAdapter()
        self.registry.register(self.adapter)
        self.service = ProviderConnectionService(self.connections, self.registry)

    def tearDown(self) -> None:
        self.connections.close()

    def register(self) -> None:
        self.service.register_verified(
            connection_id="spotify-1",
            provider="spotify",
            provider_account_id="account-1",
            manifest_version="fixture-1",
            secret_ref="secret-ref-1",
            now=NOW,
        )

    def test_verified_registration_then_probe_publishes_capabilities(self) -> None:
        self.register()
        probed = self.service.probe("spotify-1", now=NOW)
        self.assertEqual(probed.state.value, "connected")
        self.assertTrue(probed.capabilities.supports(Capability.READ_PLAYLISTS))

    def test_auth_error_requires_action_and_provider_outage_degrades(self) -> None:
        self.register()
        self.adapter.error = ProviderApiError(ProviderErrorCategory.AUTHENTICATION_REQUIRED, "expired grant")
        action_required = self.service.probe("spotify-1", now=NOW)
        self.assertEqual(action_required.state.value, "action_required")
        self.assertEqual(action_required.health_code, "authentication_required")

        self.adapter.error = ProviderApiError(ProviderErrorCategory.PROVIDER_UNAVAILABLE, "provider unavailable")
        degraded = self.service.probe("spotify-1", now=NOW)
        self.assertEqual(degraded.state.value, "degraded")
        self.assertEqual(degraded.health_code, "provider_unavailable")


if __name__ == "__main__":
    unittest.main()
