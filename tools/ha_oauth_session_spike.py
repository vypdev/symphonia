"""Isolated callback/finalization experiment with SYNTHETIC Ingress identity.

No Home Assistant login, Spotify request, real grant, or deployment occurs.
Run with PYTHONPATH=src:. python tools/ha_oauth_session_spike.py.
The callback is a real loopback HTTP listener; the management context is a
fixture, not an authentication adapter. Never install this as an HA App.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import secrets
import threading
from urllib.parse import parse_qs, urlencode, urlsplit

from symphonia.application.authorization import AuthorizationService
from symphonia.infrastructure import AuthorizationAttemptRepository
from symphonia.infrastructure.sqlite_authorization import AuthorizationAttemptError
from symphonia.providers.authorization import AuthorizationState
from symphonia.runtime.dashboard_surface import trusted_ingress_peer
from tools.oauth_callback_spike import handle_callback


CALLBACK = "/oauth/callback"
FIXTURE_REDIRECT = "https://callback.example.test" + CALLBACK
FIXTURE_ORIGIN = "https://ha.example.test"


@dataclass(frozen=True)
class SyntheticIngressContext:
    """Test inputs only: a production adapter cannot accept these from a body."""

    peer: str
    actor_id: str = field(repr=False)
    browser_nonce: str = field(repr=False)
    origin: str = FIXTURE_ORIGIN


class SessionProof:
    """One in-memory fixture attempt; no production auth or token storage."""

    def __init__(self, authorization, *, exchange, clock=None):
        self.authorization: AuthorizationService = authorization
        self.exchange = exchange
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._key = secrets.token_bytes(32)
        self._binding = b""
        self._state = ""
        self._attempt = None
        self._pending = None
        self._started = False

    def _fingerprint(self, context):
        if not isinstance(context, SyntheticIngressContext) or (
            not all(isinstance(value, str) for value in (
                context.peer, context.actor_id, context.browser_nonce, context.origin
            ))
            or
            not trusted_ingress_peer(context.peer)
            or context.origin != FIXTURE_ORIGIN
            or re.fullmatch(r"[a-f0-9]{32}", context.actor_id) is None
            or re.fullmatch(r"[A-Za-z0-9_-]{43}", context.browser_nonce) is None
        ):
            return None
        return hmac.digest(
            self._key, (context.actor_id + ":" + context.browser_nonce).encode(), "sha256"
        )

    def begin(self, context):
        with self._lock:
            binding = self._fingerprint(context)
            if binding is None:
                raise ValueError("invalid_synthetic_ingress_context")
            if self._started:
                raise ValueError("one_fixture_attempt_only")
            start = self.authorization.begin(
                provider="spotify", actor_id=context.actor_id,
                redirect_uri=FIXTURE_REDIRECT, now=self.clock(),
            )
            self._started = True
            self._attempt = start.attempt
            self._state = start.raw_state
            self._binding = binding
            return start.raw_state

    def _erase(self):
        self._pending = None
        self._state = ""
        self._binding = b""

    def _expired(self):
        if self._attempt is not None and self.clock() >= self._attempt.expires_at:
            try:
                self.authorization.deny(
                    self._attempt.attempt_id, now=self.clock(), failure_code="fixture_expired"
                )
            except AuthorizationAttemptError:
                # The repository atomically records expiry before rejecting denial.
                if self.authorization.resolve_callback(raw_state=self._state).state != AuthorizationState.EXPIRED:
                    raise
            finally:
                self._erase()
            return True
        return False

    def receive(self, path, *, provider="spotify"):
        """Stage a bounded callback; never exchange it on the direct listener."""
        with self._lock:
            if not isinstance(path, str) or len(path) > 12288 or not path.startswith("/") or path.startswith("//"):
                return 400, "invalid_callback"
            try:
                parsed = urlsplit(path)
            except ValueError:
                return 400, "invalid_callback"
            if parsed.scheme or parsed.netloc or parsed.fragment or parsed.path != CALLBACK:
                return 404, "not_found"
            try:
                query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=8)
            except ValueError:
                return 400, "invalid_callback"
            values = {}
            for name in ("state", "code", "error"):
                items = query.get(name)
                if items is not None:
                    limit = 8192 if name == "code" else 512
                    if len(items) != 1 or not items[0].strip() or len(items[0]) > limit:
                        return 400, "invalid_callback"
                    values[name] = items[0]
            if "state" not in values or ("code" in values) == ("error" in values):
                return 400, "invalid_callback"
            if not self._state or not hmac.compare_digest(
                values["state"].encode(), self._state.encode()
            ):
                return 400, "invalid_callback"
            if self._expired():
                return 400, "expired_callback"
            attempt = self.authorization.resolve_callback(raw_state=self._state)
            if (
                provider != "spotify" or attempt.provider != provider
                or attempt.redirect_uri != FIXTURE_REDIRECT
                or attempt.actor_id != self._attempt.actor_id
                or attempt.attempt_id != self._attempt.attempt_id
                or attempt.state != AuthorizationState.CREATED
            ):
                return 400, "invalid_callback"
            if self._pending is not None:
                return 409, "callback_already_received"
            # Drop provider descriptions and unknown query parameters immediately.
            # Normalize denial: no provider-controlled error text is retained.
            if "error" in values:
                values["error"] = "access_denied"
            self._pending = CALLBACK + "?" + urlencode(values)
            return 202, "awaiting_synthetic_ingress_finalization"

    def complete(self, context):
        with self._lock:
            binding = self._fingerprint(context)
            if binding is None or not self._binding or not hmac.compare_digest(binding, self._binding):
                return 403, "initiating_context_required"
            if self._expired():
                return 400, "expired_callback"
            if self._pending is None:
                return 409, "callback_not_received"
            try:
                result = handle_callback(
                    self._pending, provider="spotify", callback_path=CALLBACK,
                    authorization=self.authorization, now=self.clock(),
                )
                if result.status != 200:
                    return 400, "invalid_callback"
                if result.authorization_code is None:
                    return 200, "simulated_consent_denied"
                self.exchange(result.authorization_code)
                return 200, "simulated_exchange_completed"
            except Exception:
                # The fixture's callback must not leak an exchange exception/code.
                return 502, "simulated_exchange_failed"
            finally:
                self._erase()


class IsolatedCallbackServer(HTTPServer):
    def __init__(self, proof, *, host="127.0.0.1"):
        if host != "127.0.0.1":
            raise ValueError("loopback_fixture_only")
        self.proof = proof
        super().__init__((host, 0), IsolatedCallbackHandler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(2)
        return connection, address


class IsolatedCallbackHandler(BaseHTTPRequestHandler):
    server_version = "SymphoniaResearch"
    sys_version = ""

    def log_message(self, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self._send(code, "unsupported_research_request")

    def _send(self, status, message):
        body = message.encode()
        self.send_response(status)
        for key, value in {
            "Content-Type": "text/plain; charset=utf-8", "Content-Length": str(len(body)),
            "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            "Connection": "close",
        }.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        # Host validation is local-fixture-only; no proxy header is trusted.
        hosts = self.headers.get_all("Host", [])
        if hosts != [f"127.0.0.1:{self.server.server_port}"]:
            self._send(400, "invalid_host")
            return
        status, message = self.server.proof.receive(self.path)
        self._send(status, message)

    def do_POST(self):
        self._send(404, "not_found")


def run_simulation():
    """Exercise real local HTTP plus synthetic management contexts, then exit."""
    repository = AuthorizationAttemptRepository()
    exchanges = []
    proof = SessionProof(AuthorizationService(repository), exchange=lambda code: exchanges.append(True))
    context = SyntheticIngressContext("172.30.32.2", "a" * 32, secrets.token_urlsafe(32))
    state = proof.begin(context)
    server = IsolatedCallbackServer(proof)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
    try:
        connection.request("GET", CALLBACK + "?" + urlencode({"state": state, "code": "SYNTHETIC-CODE-ONLY"}))
        response = connection.getresponse()
        response.read()
        staged_without_exchange = response.status == 202 and not exchanges
        wrong_context = SyntheticIngressContext("172.30.32.2", "a" * 32, secrets.token_urlsafe(32))
        wrong_session_rejected = proof.complete(wrong_context)[0] == 403 and not exchanges
        correct_context_completed = proof.complete(context) == (200, "simulated_exchange_completed")
        replay_rejected = proof.complete(context)[0] == 403 and len(exchanges) == 1
        return {
            "mode": "isolated_simulation", "real_home_assistant": "not_run", "real_spotify": "not_run",
            "callback_waited_for_session": staged_without_exchange,
            "wrong_session_rejected": wrong_session_rejected,
            "initiating_context_completed": correct_context_completed,
            "exchange_once": replay_rejected,
        }
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        repository.close()


if __name__ == "__main__":
    report = run_simulation()
    print(json.dumps(report, sort_keys=True))
    checks = ("callback_waited_for_session", "wrong_session_rejected", "initiating_context_completed", "exchange_once")
    raise SystemExit(0 if all(report[key] is True for key in checks) else 1)
