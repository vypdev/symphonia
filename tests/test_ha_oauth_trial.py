from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from html.parser import HTMLParser
import http.client
import json
from pathlib import Path
import threading
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from tools.ha_oauth_trial.server import (
    CALLBACK, COOKIE, FLOW_SECONDS, RUN_SECONDS, PROFILE, TOKEN, Rejected,
    Trial, TrialHandler, TrialServer, configuration, request_json, tunnel_command,
    read_options, validate_grant, valid_token, verify_spotify,
)


OPTIONS = {"client_id": "0" * 32, "management_origin": "https://ha.example.test", "tunnel_enabled": False}
ORIGIN = "https://research-fixture.trycloudflare.com"


def headers(**changes):
    values = {"X-Remote-User-Id": "a" * 32, "X-Ingress-Path": "/api/hassio_ingress/fixture-only",
        "X-Forwarded-Proto": "https", "Cookie": "ingress_session=" + "b" * 128}
    values.update(changes)
    result = Message()
    for key, value in values.items():
        result[key] = value
    return result


class HAInstalledTrialTests(unittest.TestCase):
    def setUp(self):
        self.now, self.calls = 0, []
        self.trial = Trial(OPTIONS, clock=lambda: self.now, exchange=lambda *args: self.calls.append(args))
        self.trial.set_callback_origin(ORIGIN)
        self.identity = self.trial.identity("172.30.32.2", headers())
        self.nonce, self.csrf = self.trial.browser(self.identity, headers()["Cookie"], create=True)
        self.cookie = headers()["Cookie"] + "; " + COOKIE + "=" + self.nonce

    def begin(self):
        url = self.trial.post("/start", self.identity, self.cookie, OPTIONS["management_origin"], self.csrf)
        params = parse_qs(urlsplit(url).query)
        return params, CALLBACK + "?" + urlencode({"state": params["state"][0], "code": "code-canary"})

    def complete(self, **changes):
        return self.trial.post(changes.get("action", "/complete"), changes.get("identity", self.identity),
            changes.get("cookie", self.cookie), changes.get("origin", OPTIONS["management_origin"]), changes.get("csrf", self.csrf))

    def test_full_flow_waits_for_bound_finalization_and_erases_pending_material(self):
        params, path = self.begin()
        self.assertEqual(params["redirect_uri"], [ORIGIN + CALLBACK])
        self.assertEqual(params["scope"], ["user-read-private"])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertNotIn("client_secret", params)
        self.trial.receive(path, urlsplit(ORIGIN).netloc)
        self.assertEqual(self.calls, [])
        self.complete()
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(self.trial.flow)
        self.assertEqual(self.trial.report["result"], "spotify_pkce_verified")
        for value in ("code-canary", self.nonce, self.csrf, params["state"][0]):
            self.assertNotIn(value, json.dumps(self.trial.report))
        self.assertEqual(self.trial.report["core_login_revocation"], "not_proven")

    def test_untrusted_peer_cannot_supply_ingress_identity(self):
        for peer in ("127.0.0.1", "172.30.32.3", "::ffff:172.30.32.2"):
            with self.assertRaises(Rejected):
                self.trial.identity(peer, headers())

    def test_duplicate_or_missing_remote_actor_is_denied(self):
        for field in ("", "unknown", "A" * 32):
            with self.assertRaises(Rejected):
                self.trial.identity("172.30.32.2", headers(**{"X-Remote-User-Id": field}))
        duplicate = headers()
        duplicate["X-Remote-User-Id"] = "c" * 32
        with self.assertRaises(Rejected):
            self.trial.identity("172.30.32.2", duplicate)

    def test_http_ingress_does_not_issue_trial_session(self):
        with self.assertRaisesRegex(Rejected, "https"):
            self.trial.identity("172.30.32.2", headers(**{"X-Forwarded-Proto": "http"}))

    def test_missing_ambiguous_or_malformed_ingress_cookie_is_denied(self):
        for cookie in ("", "other=x", "ingress_session=x", "ingress_session=" + "b" * 128 + "; ingress_session=" + "c" * 128):
            with self.assertRaises(Rejected):
                self.trial.identity("172.30.32.2", headers(Cookie=cookie))

    def test_untrusted_ingress_path_is_denied(self):
        for path in ("/", "//other", "/api/hassio_ingress/x/../x", "/api/hassio_ingress/x?secret"):
            with self.assertRaises(Rejected):
                self.trial.identity("172.30.32.2", headers(**{"X-Ingress-Path": path}))

    def test_same_actor_different_supervisor_session_cannot_reuse_app_cookie(self):
        self.begin()
        other = self.trial.identity("172.30.32.2", headers(Cookie="ingress_session=" + "c" * 128))
        with self.assertRaisesRegex(Rejected, "initiating_ingress"):
            self.complete(identity=other)
        self.assertEqual(self.calls, [])

    def test_different_actor_cannot_complete(self):
        self.begin()
        other = self.trial.identity("172.30.32.2", headers(**{"X-Remote-User-Id": "d" * 32}))
        with self.assertRaises(Rejected):
            self.complete(identity=other)

    def test_same_ingress_identity_different_browser_nonce_cannot_complete(self):
        self.begin()
        nonce, csrf = self.trial.browser(self.identity, headers()["Cookie"], create=True)
        with self.assertRaisesRegex(Rejected, "initiating_browser"):
            self.complete(cookie=headers()["Cookie"] + "; " + COOKIE + "=" + nonce, csrf=csrf)
        self.assertEqual(self.calls, [])

    def test_origin_and_csrf_are_both_required(self):
        self.begin()
        for changes in ({"origin": "https://attacker.example"}, {"origin": "null"}, {"csrf": "bad"}):
            with self.assertRaisesRegex(Rejected, "origin_or_csrf"):
                self.complete(**changes)
        self.assertEqual(self.calls, [])

    def test_cookie_limit_and_unknown_nonce_fail_closed(self):
        with self.assertRaises(Rejected):
            self.complete(cookie="ingress_session=" + "b" * 128)
        for _ in range(7):
            self.trial.browser(self.identity, headers()["Cookie"], create=True)
        with self.assertRaises(Rejected):
            self.trial.browser(self.identity, headers()["Cookie"], create=True)

    def test_state_mismatch_and_query_ambiguity_never_stage(self):
        _, path = self.begin()
        for value in (path + "&state=duplicate", path + "&error=denied", CALLBACK + "?state=wrong&code=x", path + "&code=duplicate"):
            with self.assertRaises(Rejected):
                self.trial.receive(value, urlsplit(ORIGIN).netloc)
        self.assertIsNone(self.trial.flow["pending"])

    def test_callback_host_and_management_paths_are_not_accepted(self):
        _, path = self.begin()
        for route, host in ((path, "attacker.example"), ("/api/complete", urlsplit(ORIGIN).netloc),
            ("/", urlsplit(ORIGIN).netloc), (path + "#fragment", urlsplit(ORIGIN).netloc)):
            with self.assertRaises(Rejected):
                self.trial.receive(route, host)

    def test_callback_duplicates_and_completion_replay_have_one_exchange(self):
        _, path = self.begin()
        self.trial.receive(path, urlsplit(ORIGIN).netloc)
        with self.assertRaises(Rejected):
            self.trial.receive(path, urlsplit(ORIGIN).netloc)
        self.complete()
        with self.assertRaises(Rejected):
            self.complete()
        with self.assertRaises(Rejected):
            self.trial.receive(path, urlsplit(ORIGIN).netloc)
        self.assertEqual(len(self.calls), 1)

    def test_concurrent_completion_has_exactly_one_owner(self):
        _, path = self.begin()
        self.trial.receive(path, urlsplit(ORIGIN).netloc)
        def finish(_):
            try:
                self.complete()
                return "ok"
            except Rejected:
                return "rejected"
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(finish, range(2))), ["ok", "rejected"])
        self.assertEqual(len(self.calls), 1)

    def test_autonomous_expiry_erases_callback_without_another_http_request(self):
        _, path = self.begin()
        self.trial.receive(path, urlsplit(ORIGIN).netloc)
        self.now = FLOW_SECONDS
        self.assertFalse(self.trial.expire())
        self.assertIsNone(self.trial.flow)
        self.assertEqual(self.trial.report["result"], "attempt_expired")
        self.assertEqual(self.calls, [])

    def test_run_deadline_erases_all_browser_sessions(self):
        self.begin()
        self.now = RUN_SECONDS
        self.assertTrue(self.trial.expire())
        self.assertEqual(self.trial.sessions, {})
        self.assertIsNone(self.trial.flow)

    def test_denial_and_cancel_never_exchange(self):
        params, _ = self.begin()
        self.trial.receive(CALLBACK + "?" + urlencode({"state": params["state"][0], "error": "private-canary", "error_description": "secret"}), urlsplit(ORIGIN).netloc)
        self.complete()
        self.assertEqual(self.trial.report["result"], "consent_denied")
        self.assertEqual(self.calls, [])
        other = Trial(OPTIONS, exchange=lambda *args: self.fail("no exchange"))
        other.set_callback_origin(ORIGIN)
        nonce, csrf = other.browser(self.identity, headers()["Cookie"], create=True)
        cookie = headers()["Cookie"] + "; " + COOKIE + "=" + nonce
        other.post("/start", self.identity, cookie, OPTIONS["management_origin"], csrf)
        other.post("/cancel", self.identity, cookie, OPTIONS["management_origin"], csrf)
        self.assertIsNone(other.flow)

    def test_exchange_failure_does_not_leak_or_retry_credentials(self):
        def fail(*args):
            raise RuntimeError("token-canary")
        self.trial.exchange = fail
        _, path = self.begin()
        self.trial.receive(path, urlsplit(ORIGIN).netloc)
        self.complete()
        self.assertEqual(self.trial.report["result"], "provider_verification_failed")
        self.assertNotIn("canary", json.dumps(self.trial.report))
        self.assertIsNone(self.trial.flow)

    def test_restart_cannot_resume_a_pending_grant(self):
        _, path = self.begin()
        restarted = Trial(OPTIONS)
        restarted.set_callback_origin(ORIGIN)
        with self.assertRaises(Rejected):
            restarted.receive(path, urlsplit(ORIGIN).netloc)
        with self.assertRaises(Rejected):
            restarted.browser(self.identity, self.cookie)

    def test_tunnel_origin_is_fixed_and_not_arbitrary_egress(self):
        for value in (ORIGIN, "http://127.0.0.1", "https://example.com", "https://valid.trycloudflare.com/evil"):
            with self.assertRaises(Rejected):
                self.trial.set_callback_origin(value)
        fresh = Trial(OPTIONS)
        with self.assertRaises(Rejected):
            fresh.post("/start", self.identity, self.cookie, OPTIONS["management_origin"], self.csrf)

    def test_real_http_listener_isolation_and_no_secret_echo(self):
        _, path = self.begin()
        servers = [TrialServer(("127.0.0.1", 0), self.trial, callback=mode) for mode in (True, False)]
        threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]
        for thread in threads:
            thread.start()
        def request(server, method, route):
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            try:
                client.request(method, route, headers={"Host": urlsplit(ORIGIN).netloc,
                    "X-Remote-User-Id": "a" * 32, "X-Forwarded-For": "172.30.32.2", "Cookie": self.cookie})
                response = client.getresponse()
                return response.status, response.read().decode(), response.getheader("Cache-Control")
            finally:
                client.close()
        try:
            for route in ("/", "/health", "/complete", "/api/dashboard"):
                self.assertEqual(request(servers[0], "GET", route)[0], 400)
            self.assertEqual(request(servers[0], "POST", "/complete")[0], 404)
            status, body, cache = request(servers[0], "GET", path)
            self.assertEqual(status, 200)
            self.assertEqual(cache, "no-store")
            self.assertNotIn("code-canary", body)
            self.assertEqual(request(servers[1], "GET", "/")[0], 403)
            self.assertEqual(request(servers[1], "POST", "/complete")[0], 403)
            self.assertEqual(self.calls, [])
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=2)

    def test_packaging_has_no_host_ports_or_privileged_ha_access(self):
        root = Path(__file__).resolve().parents[1] / "tools/ha_oauth_trial"
        metadata = json.loads((root / "config.yaml").read_text())
        self.assertEqual(metadata["boot"], "manual")
        self.assertTrue(metadata["panel_admin"])
        self.assertFalse(metadata["options"]["tunnel_enabled"])
        for key in ("ports", "host_network", "privileged", "devices", "map", "docker_api"):
            self.assertNotIn(key, metadata)
        for key in ("homeassistant_api", "hassio_api", "auth_api"):
            self.assertFalse(metadata[key])
        dockerfile = (root / "Dockerfile").read_text()
        self.assertIn("USER root", dockerfile)  # bounded options read, then UID 10001
        self.assertEqual(dockerfile.count("@sha256:"), 2)
        self.assertIn("http://127.0.0.1:8100", tunnel_command())
        self.assertIn("127.0.0.1:20241", tunnel_command())

    def test_private_form_preserves_origin_under_core_referrer_header_override(self):
        class FormParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.meta, self.csrf = [], None
            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if tag == "meta":
                    self.meta.append(values)
                if tag == "input" and values.get("name") == "csrf":
                    self.csrf = values["value"]
        server = TrialServer(("127.0.0.1", 0), self.trial)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = http.client.HTTPConnection(*server.server_address, timeout=2)
        try:
            # Synthetic trusted adapter only inside this fixture. No HA session.
            with patch.object(TrialHandler, "ingress", return_value=self.identity):
                client.request("GET", "/")
                response = client.getresponse()
                self.assertEqual(response.status, 200)
                cookie = response.getheader("Set-Cookie").split(";", 1)[0]
                parser = FormParser()
                parser.feed(response.read().decode())
                # Core overwrites the HTTP header with no-referrer. The private
                # document therefore needs its own same-origin policy too.
                self.assertIn({"name": "referrer", "content": "same-origin"}, parser.meta)
                body = urlencode({"csrf": parser.csrf})
                for origin, expected in (("null", 403), (OPTIONS["management_origin"], 303)):
                    client.request("POST", "/start", body, headers={"Cookie": cookie,
                        "Origin": origin, "Content-Type": "application/x-www-form-urlencoded"})
                    response = client.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                self.assertEqual(self.trial.report["result"], "waiting_for_spotify")
                self.assertEqual(self.calls, [])
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_options_reject_http_credentials_paths_and_unknown_fields(self):
        for changes in ({"management_origin": "http://ha.local"}, {"management_origin": "https://user:pass@ha.test"},
            {"management_origin": "https://ha.test/path"}, {"client_id": "bad"}, {"tunnel_enabled": "true"}, {"secret": "canary"}):
            with self.assertRaises(ValueError):
                configuration({**OPTIONS, **changes})

    def test_options_reader_refuses_symlinks_and_oversized_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps(OPTIONS))
            self.assertEqual(read_options(path), OPTIONS)
            link = Path(directory) / "link.json"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                read_options(link)
            path.write_text("x" * 4097)
            with self.assertRaises(ValueError):
                read_options(path)


class TrialSpotifyTransportTests(unittest.TestCase):
    def test_fixed_minimal_exchange_and_immediate_refresh_verify_same_account(self):
        calls = []
        def transport(url, **kwargs):
            calls.append((url, kwargs))
            if url == TOKEN:
                return {"access_token": "access-canary", "refresh_token": "refresh-canary", "token_type": "Bearer", "expires_in": 3600, "scope": "user-read-private"}
            return {"id": "account-canary"}
        self.assertIsNone(verify_spotify("0" * 32, "code-canary", "verifier-canary", ORIGIN + CALLBACK, transport))
        self.assertEqual([url for url, _ in calls], [TOKEN, PROFILE, TOKEN, PROFILE])
        self.assertNotIn("client_secret", calls[0][1]["form"])
        self.assertEqual(calls[0][1]["form"]["redirect_uri"], ORIGIN + CALLBACK)

    def test_changed_account_rejects_verification(self):
        profiles = iter([{"id": "one"}, {"id": "two"}])
        def transport(url, **kwargs):
            if url == PROFILE:
                return next(profiles)
            return {"access_token": "access", "refresh_token": "refresh", "token_type": "Bearer", "expires_in": 1, "scope": "user-read-private"}
        with self.assertRaisesRegex(Rejected, "account_changed"):
            verify_spotify("0" * 32, "code", "verifier", ORIGIN + CALLBACK, transport)

    def test_scope_and_grant_validation_prevents_excess_or_malformed_access(self):
        grant = {"access_token": "access", "refresh_token": "refresh", "token_type": "Bearer", "expires_in": 1, "scope": "user-read-private"}
        for changes in ({"scope": "user-read-private playlist-modify-public"}, {"expires_in": True}, {"token_type": "Basic"}, {"refresh_token": "bad\r\n"}):
            with self.assertRaises(Rejected):
                validate_grant({**grant, **changes})
        validate_grant({key: value for key, value in grant.items() if key not in {"scope", "refresh_token"}}, refresh=True)

    def test_unapproved_endpoints_and_header_injection_fail_before_request(self):
        with self.assertRaises(Rejected):
            request_json("http://127.0.0.1/secret")
        with self.assertRaises(Rejected):
            valid_token("token\r\nInjected: yes")


if __name__ == "__main__":
    unittest.main()
