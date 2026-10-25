"""Research fixture regression tests; actual Core/TLS/backup proofs are separate."""
import json
import http.client
from pathlib import Path
import socket
import ssl
import threading
import time
import unittest

from tools.ha_oauth_companion_lab.app.server import BoundedTLSHTTPServer, Pairing


class CompanionLabFixtureTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.pair = Pairing("synthetic-challenge", clock=lambda: self.now)
        self.base = {"version": 1, "profile": "oauth", "epoch": 0}
        self.enroll = {**self.base, "op": "pair.enroll", "challenge": "synthetic-challenge"}

    def test_wrong_challenge_does_not_consume_the_valid_one(self):
        self.assertEqual(self.pair.request({**self.enroll, "challenge": "wrong"}, b"client"), 403)
        self.assertEqual(self.pair.request(self.enroll, b"client"), 200)

    def test_challenge_expires_at_exact_deadline(self):
        self.now = 400.0
        self.assertEqual(self.pair.request(self.enroll, b"client"), 403)
        self.assertIsNone(self.pair.peer)

    def test_enrollment_cannot_be_replayed_or_transferred(self):
        self.assertEqual(self.pair.request(self.enroll, b"client"), 200)
        self.assertEqual(self.pair.request(self.enroll, b"other"), 403)
        self.assertEqual(self.pair.request({**self.base, "op": "hello"}, b"other"), 403)

    def test_missing_client_identity_never_pairs(self):
        self.assertEqual(self.pair.request(self.enroll, None), 403)
        self.assertEqual(self.pair.request(self.enroll, b"client"), 200)

    def test_revocation_fences_the_old_certificate_and_epoch(self):
        self.pair.request(self.enroll, b"client")
        self.assertEqual(self.pair.request({**self.base, "op": "pair.revoke"}, b"client"), 200)
        self.assertEqual(self.pair.epoch, 1)
        for epoch in (0, 1):
            self.assertEqual(self.pair.request({**self.base, "op": "hello", "epoch": epoch}, b"client"), 403)

    def test_oauth_pair_never_acquires_playback_or_arbitrary_operations(self):
        self.pair.request(self.enroll, b"client")
        self.assertEqual(self.pair.request({**self.base, "op": "hello", "profile": "playback"}, b"client"), 403)
        for operation in ("player.command", "provider.request", "GET", ""):
            self.assertEqual(self.pair.request({**self.base, "op": operation}, b"client"), 403)

    def test_boolean_versions_and_epochs_are_not_integers(self):
        self.assertEqual(self.pair.request({**self.enroll, "version": True}, b"client"), 403)
        self.pair.request(self.enroll, b"client")
        self.assertEqual(self.pair.request({**self.base, "op": "hello", "epoch": False}, b"client"), 403)

    def test_non_objects_and_unknown_fields_are_rejected(self):
        for value in (None, [], "hello", 1):
            self.assertEqual(self.pair.request(value, b"client"), 400)
        self.assertEqual(self.pair.request({**self.enroll, "url": "https://example.invalid"}, b"client"), 400)

    def test_wrong_version_does_not_fall_back_to_plain_or_other_profile(self):
        self.assertEqual(self.pair.request({**self.enroll, "version": 2}, b"client"), 403)
        self.assertEqual(self.pair.request({**self.enroll, "profile": "unknown"}, b"client"), 403)

    def test_fixture_app_has_no_public_ports_mounts_or_core_permissions(self):
        path = Path(__file__).resolve().parents[1] / "tools/ha_oauth_companion_lab/app/app-metadata.fixture.json"
        self.assertEqual(list(path.parent.rglob("config.*")), [])
        data = json.loads(path.read_text())
        self.assertEqual(data["ports"], {})
        self.assertEqual(data["boot"], "manual")
        self.assertEqual(data["backup_exclude"], ["excluded/*"])
        for flag in ("homeassistant_api", "hassio_api", "auth_api", "docker_api", "host_network", "privileged", "map"):
            self.assertFalse(data.get(flag), flag)


class FixtureReadTimeoutTests(unittest.TestCase):
    class PeerSocket:
        def __init__(self, raw, certificate):
            self.raw, self.certificate = raw, certificate

        def __getattr__(self, name):
            return getattr(self.raw, name)

        def getpeercert(self, binary_form=False):
            return self.certificate

        def do_handshake(self):
            pass

    class IdentityTLS:
        """Only HTTP cases stub TLS; handshake case uses a real SSLContext."""
        def __init__(self, certificate=b"synthetic-client"):
            self.certificate = certificate

        def wrap_socket(self, raw, **kwargs):
            return FixtureReadTimeoutTests.PeerSocket(raw, self.certificate)

    def server(self, context, *, parse_seconds=2.0):
        server = BoundedTLSHTTPServer(("127.0.0.1", 0), context, Pairing("synthetic"),
                                      connection_timeout=0.1, parse_seconds=parse_seconds)
        self.addCleanup(server.server_close)
        return server

    def run_server(self, context, *, parse_seconds=2.0):
        server = self.server(context, parse_seconds=parse_seconds)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(server.shutdown)
        return server

    def test_stalled_real_tls_handshake_times_out_and_closes_socket(self):
        # No certificate is needed: the peer never sends a ClientHello.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server = self.server(context)
        stalled = socket.create_connection(server.server_address, timeout=2)
        self.addCleanup(stalled.close)
        worker = threading.Thread(target=server.handle_request, daemon=True)
        worker.start()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(stalled.recv(1), b"")

    def assert_next_request_served(self, server):
        healthy = http.client.HTTPConnection(*server.server_address, timeout=2)
        self.addCleanup(healthy.close)
        healthy.request("GET", "/")
        self.assertEqual(healthy.getresponse().status, 404)

    def test_stalled_headers_release_the_server_for_a_later_request(self):
        server = self.run_server(self.IdentityTLS())
        stalled = socket.create_connection(server.server_address, timeout=2)
        self.addCleanup(stalled.close)
        stalled.sendall(b"POST /internal/ha-oauth/v1 HTTP/1.1\r\nHost: fixture\r\n")
        self.assert_next_request_served(server)
        self.assertEqual(stalled.recv(1), b"")

    def test_stalled_authenticated_body_releases_the_server_for_a_later_request(self):
        server = self.run_server(self.IdentityTLS())
        stalled = socket.create_connection(server.server_address, timeout=2)
        self.addCleanup(stalled.close)
        stalled.sendall(b"POST /internal/ha-oauth/v1 HTTP/1.1\r\nHost: fixture\r\n"
                        b"Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{")
        self.assert_next_request_served(server)
        self.assertEqual(stalled.recv(1), b"")

    def test_missing_certificate_rejected_without_reading_a_body(self):
        server = self.run_server(self.IdentityTLS(certificate=None))
        client = socket.create_connection(server.server_address, timeout=2)
        self.addCleanup(client.close)
        client.sendall(b"POST /internal/ha-oauth/v1 HTTP/1.1\r\nHost: fixture\r\n"
                       b"Content-Type: application/json\r\nContent-Length: 100\r\n\r\n")
        response = http.client.HTTPResponse(client)
        response.begin()
        self.assertEqual(response.status, 403)
        response.read()
        self.assert_next_request_served(server)

    def test_truncated_valid_json_does_not_consume_enrollment_challenge(self):
        server = self.run_server(self.IdentityTLS())
        body = json.dumps({"op": "pair.enroll", "version": 1, "profile": "oauth",
                           "challenge": "synthetic"}).encode()
        client = socket.create_connection(server.server_address, timeout=2)
        self.addCleanup(client.close)
        client.sendall(b"POST /internal/ha-oauth/v1 HTTP/1.1\r\nHost: fixture\r\n"
                       b"Content-Type: application/json\r\nContent-Length: "
                       + str(len(body) + 1).encode() + b"\r\n\r\n" + body)
        client.shutdown(socket.SHUT_WR)
        response = http.client.HTTPResponse(client)
        response.begin()
        self.assertEqual(response.status, 400)
        response.read()
        self.assertEqual(server.pairing.challenge, "synthetic")
        self.assertIsNone(server.pairing.peer)
        healthy = http.client.HTTPConnection(*server.server_address, timeout=2)
        self.addCleanup(healthy.close)
        healthy.request("POST", "/internal/ha-oauth/v1", body=body,
                        headers={"Content-Type": "application/json"})
        response = healthy.getresponse()
        self.assertEqual(response.status, 200)
        response.read()
        self.assertIsNone(server.pairing.challenge)

    def test_trickled_real_tls_handshake_has_a_total_deadline(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server = self.server(context, parse_seconds=0.15)
        client = socket.create_connection(server.server_address, timeout=2)
        self.addCleanup(client.close)
        worker = threading.Thread(target=server.handle_request, daemon=True)
        worker.start()
        # An incomplete TLS handshake record, delivered within the idle window.
        client.sendall(b"\x16\x03\x01\x00\x50\x01\x00\x00\x4c")
        for _ in range(12):
            try:
                client.sendall(b"\x00")
            except OSError:
                break
            time.sleep(0.02)
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertIsNone(server._parsing)

    def assert_trickled_http_releases_listener(self, body):
        server = self.run_server(self.IdentityTLS(), parse_seconds=0.15)
        client = socket.create_connection(server.server_address, timeout=2)
        self.addCleanup(client.close)
        request = b"POST /internal/ha-oauth/v1 HTTP/1.1\r\nHost: fixture\r\n"
        request += (b"Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{"
                    if body else b"X-Slow: ")
        client.sendall(request)
        for _ in range(12):
            try:
                client.sendall(b" ")
            except OSError:
                break
            time.sleep(0.02)
        self.assert_next_request_served(server)
        self.assertEqual(server.pairing.challenge, "synthetic")
        self.assertIsNone(server.pairing.peer)

    def test_trickled_authenticated_headers_release_the_listener(self):
        self.assert_trickled_http_releases_listener(False)

    def test_trickled_authenticated_body_releases_the_listener(self):
        self.assert_trickled_http_releases_listener(True)


if __name__ == "__main__":
    unittest.main()
