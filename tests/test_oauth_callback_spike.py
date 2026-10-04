from __future__ import annotations

from datetime import datetime, timezone
import http.client
import threading
import unittest

from symphonia.application import AuthorizationService
from symphonia.infrastructure import AuthorizationAttemptRepository
from symphonia.providers import AuthorizationState
from tools.oauth_callback_spike import create_callback_server, handle_callback


NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


class OAuthCallbackSpikeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = AuthorizationAttemptRepository()
        self.service = AuthorizationService(
            self.repository,
            state_factory=lambda: "state-for-callback",
            id_factory=lambda: "attempt-1",
        )
        self.service.begin(
            provider="spotify",
            actor_id="ha-user-1",
            redirect_uri="https://ha.example/symphonia/oauth/callback",
            now=NOW,
        )

    def tearDown(self) -> None:
        self.repository.close()

    def test_success_consumes_state_and_does_not_echo_code(self) -> None:
        result = handle_callback(
            "/oauth/callback?state=state-for-callback&code=secret-provider-code",
            provider="spotify",
            callback_path="/oauth/callback",
            authorization=self.service,
            now=NOW,
        )

        self.assertEqual(result.status, 200)
        self.assertEqual(result.authorization_code, "secret-provider-code")
        self.assertEqual(result.attempt.state, AuthorizationState.CONSUMED)
        self.assertNotIn("secret-provider-code", result.message)

    def test_wrong_route_is_not_a_management_or_callback_surface(self) -> None:
        result = handle_callback(
            "/health",
            provider="spotify",
            callback_path="/oauth/callback",
            authorization=self.service,
            now=NOW,
        )

        self.assertEqual(result.status, 404)
        self.assertEqual(self.repository.get("attempt-1").state, AuthorizationState.CREATED)

    def test_wrong_provider_does_not_consume_state(self) -> None:
        result = handle_callback(
            "/oauth/callback?state=state-for-callback&code=provider-code",
            provider="youtube_data",
            callback_path="/oauth/callback",
            authorization=self.service,
            now=NOW,
        )

        self.assertEqual(result.status, 400)
        self.assertEqual(self.repository.get("attempt-1").state, AuthorizationState.CREATED)

    def test_replay_is_rejected_without_returning_the_code(self) -> None:
        first = handle_callback(
            "/oauth/callback?state=state-for-callback&code=provider-code",
            provider="spotify",
            callback_path="/oauth/callback",
            authorization=self.service,
            now=NOW,
        )
        replay = handle_callback(
            "/oauth/callback?state=state-for-callback&code=provider-code",
            provider="spotify",
            callback_path="/oauth/callback",
            authorization=self.service,
            now=NOW,
        )

        self.assertEqual(first.status, 200)
        self.assertEqual(replay.status, 400)
        self.assertIsNone(replay.authorization_code)
        self.assertNotIn("provider-code", replay.message)

    def test_denial_records_a_safe_terminal_state(self) -> None:
        result = handle_callback(
            "/oauth/callback?state=state-for-callback&error=access_denied&error_description=secret-detail",
            provider="spotify",
            callback_path="/oauth/callback",
            authorization=self.service,
            now=NOW,
        )

        self.assertEqual(result.status, 200)
        self.assertEqual(result.attempt.state, AuthorizationState.DENIED)
        self.assertNotIn("secret-detail", result.message)

    def test_duplicate_state_parameter_is_rejected_without_consumption(self) -> None:
        result = handle_callback(
            "/oauth/callback?state=one&state=two&code=provider-code",
            provider="spotify",
            callback_path="/oauth/callback",
            authorization=self.service,
            now=NOW,
        )

        self.assertEqual(result.status, 400)
        self.assertEqual(self.repository.get("attempt-1").state, AuthorizationState.CREATED)

    def test_spike_server_is_loopback_only(self) -> None:
        with self.assertRaises(ValueError):
            create_callback_server(
                authorization=self.service,
                provider="spotify",
                clock=lambda: NOW,
                host="0.0.0.0",
            )

    def test_loopback_http_boundary_consumes_callback_without_leaking_code(self) -> None:
        try:
            server = create_callback_server(
                authorization=self.service,
                provider="spotify",
                clock=lambda: NOW,
                host="127.0.0.1",
                port=0,
            )
        except PermissionError:
            self.skipTest("the test sandbox does not permit local socket binding")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            connection = http.client.HTTPConnection(host, port, timeout=2)
            try:
                connection.request("GET", "/health")
                wrong_route = connection.getresponse()
                self.assertEqual(wrong_route.status, 404)
                self.assertEqual(self.repository.get("attempt-1").state, AuthorizationState.CREATED)

                connection.request(
                    "GET",
                    "/oauth/callback?state=state-for-callback&code=secret-http-code",
                )
                callback = connection.getresponse()
                body = callback.read().decode("utf-8")
            finally:
                connection.close()

            self.assertEqual(callback.status, 200)
            self.assertNotIn("secret-http-code", body)
            self.assertEqual(
                callback.getheader("Cache-Control"),
                "no-store",
            )
            self.assertEqual(self.repository.get("attempt-1").state, AuthorizationState.CONSUMED)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
