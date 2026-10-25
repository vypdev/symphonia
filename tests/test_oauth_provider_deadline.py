"""Real loopback I/O for the disposable provider worker; no Spotify requests."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from tools.ha_oauth_trial.server import (
    RUN_SECONDS, TOKEN, Rejected, Trial, bounded_provider_response, request_json,
)
from tools.spotify_oauth_spike import ProofError, request_json as spike_request_json


class ProviderDeadlineTests(unittest.TestCase):
    def server(self, mode):
        entered, stopped = threading.Event(), threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if mode == "redirect":
                    self.send_response(302)
                    self.send_header("Location", "/must-not-follow")
                    self.end_headers()
                    return
                if mode == "success":
                    body = b'{"safe":true}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                try:
                    if mode == "headers":
                        self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Slow: ")
                    else:
                        self.send_response(200)
                        self.end_headers()
                    entered.set()
                    while True:
                        self.wfile.write(b"x")
                        time.sleep(0.02)
                except OSError:
                    stopped.set()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        return Request(f"http://127.0.0.1:{server.server_port}/"), entered, stopped

    def assert_trickle_stopped(self, mode):
        request, entered, stopped = self.server(mode)
        started = time.monotonic()
        with self.assertRaisesRegex(TimeoutError, "^provider_deadline$"):
            bounded_provider_response(request, seconds=0.8)
        self.assertTrue(entered.is_set(), "worker must reach the actual HTTP read")
        self.assertLess(time.monotonic() - started, 3)
        # A killed/reaped worker releases the peer, not a surviving I/O thread.
        self.assertTrue(stopped.wait(2))

    def test_trickled_response_headers_have_an_absolute_deadline(self):
        self.assert_trickle_stopped("headers")

    def test_trickled_response_body_has_an_absolute_deadline(self):
        self.assert_trickle_stopped("body")

    def test_worker_returns_success_and_refuses_redirects(self):
        request, _, _ = self.server("success")
        self.assertEqual(bounded_provider_response(request), b'{"safe":true}')
        request, _, _ = self.server("redirect")
        with self.assertRaises(HTTPError) as result:
            bounded_provider_response(request)
        self.assertEqual(result.exception.code, 302)
        result.exception.close()

    def test_deadline_is_a_fixed_error_in_both_research_clients(self):
        for client, expected in ((request_json, Rejected), (spike_request_json, ProofError)):
            with self.subTest(client=client.__module__):
                with patch(client.__module__ + ".bounded_provider_response", side_effect=TimeoutError("synthetic-secret")):
                    with self.assertRaisesRegex(expected, "^provider_unreachable$"):
                        client(TOKEN, form={"code": "synthetic-code"})

    def test_expired_trial_cannot_start_a_provider_worker(self):
        now = [100.0]
        trial = Trial({"client_id": "opaque", "management_origin": "https://example.test",
                       "tunnel_enabled": False}, clock=lambda: now[0])
        now[0] += RUN_SECONDS
        with patch("tools.ha_oauth_trial.server.subprocess.run") as process:
            with self.assertRaisesRegex(Rejected, "^provider_unreachable$"):
                trial._verify("opaque", "synthetic-code", "synthetic-verifier", "https://example.test/callback")
            process.assert_not_called()
