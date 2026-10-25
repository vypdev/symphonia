from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.server import HTTPServer
import http.client
import io
import json
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit

from symphonia.application.authorization import AuthorizationService
from symphonia.infrastructure import AuthorizationAttemptRepository
from tools.spotify_oauth_spike import (
    AUTHORIZE, CALLBACK, COOKIE, PROFILE, REDIRECT, SCOPE, TOKEN,
    ProofError, ResearchHandler, SpotifyProof, challenge, request_json,
)


NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)
CANARY = "synthetic-sensitive-canary"


class SpotifyOAuthProofTests(unittest.TestCase):
    def setUp(self):
        self.repository = AuthorizationAttemptRepository()
        self.addCleanup(self.repository.close)
        self.clock = Mock(return_value=NOW)
        grant = {"access_token": CANARY, "refresh_token": CANARY, "token_type": "Bearer", "expires_in": 3600, "scope": SCOPE}
        self.transport = Mock(side_effect=[grant, {"id": "synthetic-account"}, {k: v for k, v in grant.items() if k != "refresh_token"}, {"id": "synthetic-account"}])
        self.proof = SpotifyProof("a" * 32, AuthorizationService(self.repository), transport=self.transport, clock=self.clock)
        self.url, self.cookie = self.proof.begin()
        self.parameters = parse_qs(urlsplit(self.url).query)
        self.path = CALLBACK + "?" + urlencode({"state": self.parameters["state"][0], "code": CANARY})

    def complete(self):
        return self.proof.callback(self.path, f"{COOKIE}={self.cookie}")

    def test_pkce_matches_the_rfc7636_s256_vector(self):
        self.assertEqual(challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"), "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")

    def test_opaque_client_id_stays_one_encoded_parameter_and_reaches_exchange(self):
        client = "UPPER_id&redirect_uri=https://example.invalid"
        proof = SpotifyProof(client, AuthorizationService(self.repository),
            transport=self.transport, clock=self.clock)
        url, cookie = proof.begin()
        values = parse_qs(urlsplit(url).query)
        self.assertEqual(values["client_id"], [client])
        self.assertEqual(values["redirect_uri"], [REDIRECT])
        path = CALLBACK + "?" + urlencode({"state": values["state"][0], "code": CANARY})
        self.assertEqual(proof.callback(path, f"{COOKIE}={cookie}")[0], 200)
        self.assertEqual(self.transport.call_args_list[0].kwargs["form"]["client_id"], client)

    def test_client_id_controls_types_and_tooling_size_limit_are_rejected(self):
        for client in (None, 1, "", "bad\nvalue", "bad\x00value", "bad\x7fvalue", "é", "x" * 257):
            with self.subTest(client=repr(client)), self.assertRaises(ValueError):
                SpotifyProof(client, AuthorizationService(self.repository))

    def test_requests_exact_redirect_and_only_read_only_profile_scope(self):
        self.assertTrue(self.url.startswith(AUTHORIZE + "?"))
        self.assertEqual(self.parameters["redirect_uri"], [REDIRECT])
        self.assertEqual(self.parameters["scope"], [SCOPE])
        self.assertEqual(self.parameters["code_challenge_method"], ["S256"])
        self.assertNotIn("client_secret", self.parameters)
        self.assertNotIn("code_verifier", self.parameters)

    def test_missing_or_wrong_browser_binding_prevents_exchange(self):
        for header in ("", f"{COOKIE}=wrong"):
            with self.subTest(header=header):
                status, _ = self.proof.callback(self.path, header)
                self.assertEqual(status, 400)
        self.transport.assert_not_called()

    def test_wrong_state_is_rejected_before_exchange(self):
        self.path = CALLBACK + "?state=wrong&code=" + CANARY
        self.assertEqual(self.complete()[0], 400)
        self.transport.assert_not_called()

    def test_expired_callback_is_rejected_before_exchange(self):
        self.clock.return_value = NOW + timedelta(minutes=11)
        self.assertEqual(self.complete()[0], 400)
        self.transport.assert_not_called()

    def test_callback_cannot_mix_code_and_error(self):
        self.path += "&error=access_denied"
        self.assertEqual(self.complete()[0], 400)
        self.transport.assert_not_called()

    def test_consent_denial_clears_transient_binding_without_exchange(self):
        self.path = CALLBACK + "?" + urlencode({"state": self.parameters["state"][0], "error": "access_denied"})
        status, result = self.complete()
        self.assertEqual((status, result["result"]), (200, "consent_denied"))
        self.assertFalse(self.proof._cookie)
        self.assertFalse(self.proof._verifier)
        self.transport.assert_not_called()

    def test_exchange_profile_refresh_and_same_account_are_verified_without_retaining_secrets(self):
        status, result = self.complete()
        self.assertEqual((status, result["result"]), (200, "spotify_pkce_verified"))
        self.assertTrue(result["refresh_verified"])
        self.assertEqual(result["home_assistant_actor_binding"], "not_proven")
        self.assertNotIn(CANARY, json.dumps(result))
        self.assertNotIn("synthetic-account", json.dumps(result))
        self.assertFalse(self.proof._verifier)
        self.assertFalse(self.proof._cookie)
        calls = self.transport.call_args_list
        self.assertEqual([call.args[0] for call in calls], [TOKEN, PROFILE, TOKEN, PROFILE])
        self.assertEqual(calls[2].kwargs["form"]["refresh_token"], CANARY)
        self.assertNotIn("client_secret", calls[0].kwargs["form"])

    def test_replay_cannot_exchange_the_code_twice(self):
        self.complete()
        self.assertEqual(self.complete()[0], 400)
        self.assertEqual(self.transport.call_count, 4)

    def test_provider_failure_has_only_a_fixed_error_and_discards_verifier(self):
        self.transport.side_effect = ProofError("provider_http_403")
        status, result = self.complete()
        self.assertEqual((status, result["result"]), (502, "provider_http_403"))
        self.assertNotIn(CANARY, json.dumps(result))
        self.assertFalse(self.proof._verifier)

    def test_extra_or_malformed_grants_do_not_reach_the_profile(self):
        valid = {"access_token": CANARY, "refresh_token": CANARY, "token_type": "Bearer", "expires_in": 3600, "scope": SCOPE}
        for override in ({"scope": SCOPE + " playlist-modify-private"}, {"token_type": None}, {"expires_in": True}, {"access_token": "unsafe\r\nheader"}):
            with self.subTest(override=override):
                proof = SpotifyProof("a" * 32, AuthorizationService(self.repository), transport=Mock(return_value={**valid, **override}), clock=self.clock)
                url, cookie = proof.begin()
                state = parse_qs(urlsplit(url).query)["state"][0]
                status, _ = proof.callback(CALLBACK + "?" + urlencode({"state": state, "code": CANARY}), f"{COOKIE}={cookie}")
                self.assertEqual(status, 502)
                self.assertEqual(proof.transport.call_count, 1)

    def test_refresh_cannot_silently_change_account(self):
        grant = {"access_token": CANARY, "refresh_token": CANARY, "token_type": "Bearer", "expires_in": 3600, "scope": SCOPE}
        self.transport.side_effect = [grant, {"id": "account-a"}, grant, {"id": "account-b"}]
        self.assertEqual(self.complete()[1]["result"], "provider_account_changed")

    def test_authenticated_redirect_error_never_exposes_body_or_credentials(self):
        opener = Mock()
        opener.open.side_effect = HTTPError(TOKEN, 302, CANARY, {}, io.BytesIO(CANARY.encode()))
        with patch("tools.spotify_oauth_spike.build_opener", return_value=opener):
            with self.assertRaisesRegex(ProofError, "^provider_http_302$"):
                request_json(TOKEN, form={"code": CANARY})

    def test_no_arbitrary_token_endpoints_or_oversized_provider_body(self):
        with self.assertRaises(ValueError):
            request_json("https://untrusted.invalid/token", form={"code": CANARY})
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b"x" * 65537
        opener = Mock()
        opener.open.return_value = response
        with patch("tools.spotify_oauth_spike.build_opener", return_value=opener), self.assertRaisesRegex(ProofError, "provider_response_too_large"):
            request_json(PROFILE, bearer=CANARY)

    def test_http_rejects_cross_origin_start_and_management_paths(self):
        server = HTTPServer(("127.0.0.1", 0), ResearchHandler)
        server.proof = self.proof
        server.report = None
        server.result_viewed = False
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
            for method, path, headers, expected in (
                ("GET", "/", {"Host": "127.0.0.1:8765"}, 200),
                ("GET", "/api/dashboard", {"Host": "127.0.0.1:8765"}, 404),
                ("GET", "/", {"Host": "untrusted.invalid"}, 400),
                ("POST", "/start", {"Host": "127.0.0.1:8765", "Origin": "https://untrusted.invalid"}, 400),
                ("POST", "/start", {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}, 303),
            ):
                with self.subTest(method=method, path=path, headers=headers):
                    connection.request(method, path, headers=headers)
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected)
                    self.assertEqual(response.getheader("Referrer-Policy"), "same-origin" if path == "/" and expected == 200 else "no-referrer")
                    if path == "/" and expected == 200:
                        self.assertIn("form-action 'self' https://accounts.spotify.com;", response.getheader("Content-Security-Policy"))
                    self.assertNotIn(CANARY, response.read().decode())
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
