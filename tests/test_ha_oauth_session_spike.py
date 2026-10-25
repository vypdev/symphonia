from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import http.client
import json
import socket
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from symphonia.application.authorization import AuthorizationService
from symphonia.infrastructure import AuthorizationAttemptRepository
from symphonia.providers.authorization import AuthorizationState
from tools.ha_oauth_session_spike import (
    CALLBACK, IsolatedCallbackServer, SessionProof, SyntheticIngressContext,
    run_simulation,
)


class HASessionSpikeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        self.repository = AuthorizationAttemptRepository()
        self.authorization = AuthorizationService(self.repository)
        self.exchanges = []
        self.context = SyntheticIngressContext("172.30.32.2", "a" * 32, "b" * 43)
        self.proof = SessionProof(
            self.authorization, exchange=self.exchanges.append, clock=lambda: self.now
        )
        self.state = self.proof.begin(self.context)
        self.path = CALLBACK + "?" + urlencode({"state": self.state, "code": "fixture-code-canary"})

    def tearDown(self):
        self.repository.close()

    def test_trickled_headers_release_callback_without_staging_the_state(self):
        server = IsolatedCallbackServer(self.proof, parse_seconds=0.15)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = socket.create_connection(server.server_address, timeout=2)
        healthy = http.client.HTTPConnection(*server.server_address, timeout=2)
        try:
            client.sendall(b"GET /oauth/callback HTTP/1.1\r\nX-Slow: ")
            for _ in range(12):
                try:
                    client.sendall(b"x")
                except OSError:
                    break
                time.sleep(0.02)
            self.assertIsNone(self.proof._pending)
            healthy.request("GET", self.path)
            response = healthy.getresponse()
            self.assertEqual(response.status, 202)
            response.read()
            self.assertEqual(self.exchanges, [])
            self.assertEqual(self.proof.complete(self.context)[0], 200)
        finally:
            client.close()
            healthy.close()
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_callback_stages_until_initiating_context_completes(self):
        self.assertEqual(self.proof.receive(self.path)[0], 202)
        self.assertEqual(self.exchanges, [])
        self.assertEqual(self.authorization.resolve_callback(raw_state=self.state).state, AuthorizationState.CREATED)
        self.assertEqual(self.proof.complete(self.context), (200, "simulated_exchange_completed"))
        self.assertEqual(self.exchanges, ["fixture-code-canary"])
        self.assertIsNone(self.proof._pending)
        self.assertEqual(self.proof._binding, b"")
        self.assertEqual(self.proof._state, "")

    def test_same_actor_from_different_browser_cannot_finalize(self):
        self.proof.receive(self.path)
        other = replace(self.context, browser_nonce="c" * 43)
        self.assertEqual(self.proof.complete(other)[0], 403)
        self.assertEqual(self.exchanges, [])
        self.assertEqual(self.proof.complete(self.context)[0], 200)

    def test_different_actor_with_same_browser_nonce_cannot_finalize(self):
        self.proof.receive(self.path)
        self.assertEqual(self.proof.complete(replace(self.context, actor_id="c" * 32))[0], 403)
        self.assertEqual(self.exchanges, [])

    def test_untrusted_peer_cannot_start_or_finalize(self):
        context = replace(self.context, peer="127.0.0.1")
        other = SessionProof(self.authorization, exchange=self.exchanges.append)
        with self.assertRaisesRegex(ValueError, "invalid_synthetic"):
            other.begin(context)
        self.proof.receive(self.path)
        self.assertEqual(self.proof.complete(context)[0], 403)
        self.assertEqual(self.exchanges, [])

    def test_cross_origin_cannot_start_or_finalize(self):
        context = replace(self.context, origin="https://attacker.example.test")
        with self.assertRaisesRegex(ValueError, "invalid_synthetic"):
            self.proof.begin(context)
        self.proof.receive(self.path)
        self.assertEqual(self.proof.complete(context)[0], 403)
        self.assertEqual(self.exchanges, [])

    def test_missing_or_malformed_identity_fails_closed(self):
        for context in (
            None, replace(self.context, actor_id=""), replace(self.context, actor_id=None),
            replace(self.context, browser_nonce=""), replace(self.context, browser_nonce="b" * 42),
        ):
            with self.subTest(context=context):
                self.assertEqual(self.proof.complete(context)[0], 403)

    def test_wrong_state_and_provider_do_not_stage_or_exchange(self):
        self.assertEqual(self.proof.receive(CALLBACK + "?state=wrong&code=canary")[0], 400)
        self.assertEqual(self.proof.receive(self.path, provider="other_provider")[0], 400)
        self.assertIsNone(self.proof._pending)
        self.assertEqual(self.exchanges, [])
        self.assertEqual(self.proof.receive(self.path)[0], 202)

    def test_changed_attempt_metadata_never_stages_callback(self):
        attempt = self.authorization.resolve_callback(raw_state=self.state)
        for changed in (
            replace(attempt, redirect_uri="https://different.example.test/oauth/callback"),
            replace(attempt, provider="other_provider"),
            replace(attempt, actor_id="d" * 32),
            replace(attempt, attempt_id="different-attempt"),
        ):
            with self.subTest(redirect_changed=changed.redirect_uri != attempt.redirect_uri):
                with patch.object(AuthorizationService, "resolve_callback", return_value=changed):
                    self.assertEqual(self.proof.receive(self.path)[0], 400)
        self.assertIsNone(self.proof._pending)
        self.assertEqual(self.exchanges, [])

    def test_expired_callback_is_erased_at_exact_deadline(self):
        self.now += timedelta(minutes=10)
        self.assertEqual(self.proof.receive(self.path), (400, "expired_callback"))
        self.assertIsNone(self.proof._pending)
        self.assertEqual(self.authorization.resolve_callback(raw_state=self.state).state, AuthorizationState.EXPIRED)
        self.assertEqual(self.exchanges, [])

    def test_expired_finalization_erases_pending_code(self):
        self.proof.receive(self.path)
        self.now += timedelta(minutes=10)
        self.assertEqual(self.proof.complete(self.context), (400, "expired_callback"))
        self.assertIsNone(self.proof._pending)
        self.assertEqual(self.exchanges, [])

    def test_replay_cannot_exchange_twice(self):
        self.proof.receive(self.path)
        self.proof.complete(self.context)
        self.assertEqual(self.proof.receive(self.path)[0], 400)
        self.assertEqual(self.proof.complete(self.context)[0], 403)
        self.assertEqual(len(self.exchanges), 1)

    def test_duplicate_callback_cannot_replace_original_code(self):
        self.proof.receive(self.path)
        replacement = CALLBACK + "?" + urlencode({"state": self.state, "code": "replacement-code"})
        self.assertEqual(self.proof.receive(replacement)[0], 409)
        self.proof.complete(self.context)
        self.assertEqual(self.exchanges, ["fixture-code-canary"])

    def test_ambiguous_and_oversized_query_never_stages(self):
        for path in (
            self.path + "&state=duplicate", self.path + "&error=access_denied",
            CALLBACK + "?state=" + self.state, self.path + "&code=duplicate",
            CALLBACK + "?state=" + self.state + "&code=" + "x" * 8193,
            self.path + "&" + "&".join("extra=x" for _ in range(9)),
        ):
            with self.subTest(length=len(path)):
                self.assertEqual(self.proof.receive(path)[0], 400)
        self.assertIsNone(self.proof._pending)
        self.assertEqual(self.exchanges, [])

    def test_denial_never_exchanges_or_retains_provider_error_text(self):
        path = CALLBACK + "?" + urlencode({
            "state": self.state, "error": "provider-canary", "error_description": "private-description-canary"
        })
        self.assertEqual(self.proof.receive(path)[0], 202)
        self.assertNotIn("canary", self.proof._pending)
        self.assertEqual(self.proof.complete(self.context), (200, "simulated_consent_denied"))
        self.assertEqual(self.exchanges, [])
        self.assertIsNone(self.proof._pending)

    def test_completion_before_callback_does_not_consume_attempt(self):
        self.assertEqual(self.proof.complete(self.context)[0], 409)
        self.assertEqual(self.authorization.resolve_callback(raw_state=self.state).state, AuthorizationState.CREATED)
        self.assertEqual(self.exchanges, [])

    def test_exchange_failure_is_sanitized_and_not_retried(self):
        def broken(code):
            self.exchanges.append(code)
            raise RuntimeError("private-token-canary")
        self.proof.exchange = broken
        self.proof.receive(self.path)
        self.assertEqual(self.proof.complete(self.context), (502, "simulated_exchange_failed"))
        self.assertEqual(self.proof.complete(self.context)[0], 403)
        self.assertEqual(len(self.exchanges), 1)
        self.assertIsNone(self.proof._pending)

    def test_concurrent_completion_has_one_exchange_owner(self):
        self.proof.receive(self.path)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(self.proof.complete, [self.context, self.context]))
        self.assertEqual(sorted(status for status, _ in results), [200, 403])
        self.assertEqual(len(self.exchanges), 1)

    def test_restart_abandons_transient_code_instead_of_resuming_exchange(self):
        self.proof.receive(self.path)
        restarted = SessionProof(self.authorization, exchange=self.exchanges.append, clock=lambda: self.now)
        self.assertEqual(restarted.receive(self.path)[0], 400)
        self.assertEqual(restarted.complete(self.context)[0], 403)
        self.assertEqual(self.exchanges, [])

    def test_fixture_context_repr_redacts_identity_and_nonce(self):
        self.assertNotIn(self.context.actor_id, repr(self.context))
        self.assertNotIn(self.context.browser_nonce, repr(self.context))
        with self.assertRaisesRegex(ValueError, "one_fixture_attempt_only"):
            self.proof.begin(self.context)

    def test_direct_http_callback_ignores_forged_identity_and_has_no_management_routes(self):
        server = IsolatedCallbackServer(self.proof)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def request(method, path, headers=None):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                try:
                    connection.request(method, path, headers=headers or {})
                    response = connection.getresponse()
                    return response.status, response.read().decode(), dict(response.getheaders())
                finally:
                    connection.close()
            for path in ("/", "/health", "/api/dashboard", "/api/complete", "//attacker/callback"):
                self.assertIn(request("GET", path)[0], {400, 404})
            self.assertEqual(request("POST", "/api/complete")[0], 404)
            self.assertEqual(request("GET", self.path, {"Host": "attacker.example"})[0], 400)
            status, body, headers = request("GET", self.path, {
                "X-Remote-User-Id": self.context.actor_id,
                "X-Forwarded-For": "172.30.32.2", "Cookie": "fixture=" + self.context.browser_nonce,
            })
            self.assertEqual(status, 202)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertNotIn("fixture-code-canary", body)
            self.assertNotIn(self.state, body)
            self.assertEqual(self.exchanges, [])
            self.assertEqual(self.proof.complete(replace(self.context, peer="127.0.0.1"))[0], 403)
            self.assertEqual(self.proof.complete(self.context)[0], 200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_listener_refuses_non_loopback_bind(self):
        with self.assertRaisesRegex(ValueError, "loopback_fixture_only"):
            IsolatedCallbackServer(self.proof, host="0.0.0.0")

    def test_runnable_simulation_reports_only_bounded_flags(self):
        report = run_simulation()
        self.assertEqual(report["mode"], "isolated_simulation")
        self.assertEqual(report["real_home_assistant"], "not_run")
        self.assertEqual(report["real_spotify"], "not_run")
        self.assertTrue(all(value for value in report.values() if isinstance(value, bool)))
        self.assertNotIn("canary", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
