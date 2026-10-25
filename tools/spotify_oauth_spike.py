"""Ephemeral, read-only Spotify PKCE research client; not App authorization.

Run with PYTHONPATH=src:. python tools/spotify_oauth_spike.py --client-id ID.
Register http://127.0.0.1:8765/oauth/callback in a dedicated test application.
All grant material stays in process memory and is erased after the proof.
This does not establish a Home Assistant actor or remotely reachable callback.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler
import json
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request

from symphonia.application.authorization import AuthorizationService
from symphonia.infrastructure import AuthorizationAttemptRepository
from tools.oauth_callback_spike import handle_callback
from tools.ha_oauth_trial.server import RequestDeadlineServer, bounded_provider_response


ORIGIN = "http://127.0.0.1:8765"
CALLBACK = "/oauth/callback"
REDIRECT = ORIGIN + CALLBACK
AUTHORIZE = "https://accounts.spotify.com/authorize"
TOKEN = "https://accounts.spotify.com/api/token"
PROFILE = "https://api.spotify.com/v1/me"
SCOPE = "user-read-private"
COOKIE = "symphonia_spike"


class ProofError(Exception):
    """Only fixed diagnostic codes may cross the research boundary."""


def challenge(verifier: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier) is None:
        raise ValueError("invalid PKCE verifier")
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def request_json(url: str, *, form: dict[str, str] | None = None, bearer: str | None = None, seconds=10) -> dict:
    """Fixed TLS endpoints, no redirects/proxies, bounded responses, safe errors."""
    if url not in {TOKEN, PROFILE}:
        raise ValueError("unsupported research endpoint")
    headers = {"Accept": "application/json"}
    data = None
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urlencode(form).encode("ascii")
    if bearer is not None:
        headers["Authorization"] = "Bearer " + bearer
    request = Request(url, data=data, headers=headers)
    try:
        body = bounded_provider_response(request, seconds=seconds)
    except HTTPError as error:
        status = error.code
        error.close()
        raise ProofError(f"provider_http_{status}") from None
    except (URLError, OSError, TimeoutError):
        raise ProofError("provider_unreachable") from None
    if len(body) > 65536:
        raise ProofError("provider_response_too_large")
    try:
        result = json.loads(body)
    except (ValueError, UnicodeError):
        raise ProofError("provider_invalid_json") from None
    if not isinstance(result, dict):
        raise ProofError("provider_invalid_object")
    return result


def _token(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9._~+/-]{1,8192}={0,2}", value) is None:
        raise ProofError("provider_invalid_token")
    return value


def _validate_grant(grant: dict, *, previous_scope: str | None = None) -> None:
    expires = grant.get("expires_in")
    token_type = grant.get("token_type")
    if not isinstance(token_type, str) or token_type.lower() != "bearer" or type(expires) is not int or expires <= 0:
        raise ProofError("provider_invalid_grant")
    scope = grant.get("scope", previous_scope)
    if not isinstance(scope, str) or set(scope.split()) != {SCOPE}:
        raise ProofError("provider_unexpected_scopes")
    _token(grant.get("access_token"))


class SpotifyProof:
    def __init__(self, client_id: str, authorization: AuthorizationService, *, transport=request_json, clock=None):
        # Opaque OAuth identifier, not a promised Spotify hexadecimal format.
        # The 256-character cap is a research-tool bound, not a provider limit.
        if (not isinstance(client_id, str) or not 1 <= len(client_id) <= 256
                or any(not 0x20 <= ord(char) <= 0x7e for char in client_id)):
            raise ValueError("invalid Spotify Client ID")
        self.client_id = client_id
        self.authorization = authorization
        self.transport = transport
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._verifier = ""
        self._cookie = ""

    def begin(self) -> tuple[str, str]:
        self._verifier = secrets.token_urlsafe(48)
        self._cookie = secrets.token_urlsafe(32)
        start = self.authorization.begin(provider="spotify", actor_id="synthetic-research-operator", redirect_uri=REDIRECT, now=self.clock())
        parameters = {
            "client_id": self.client_id, "response_type": "code", "redirect_uri": REDIRECT,
            "scope": SCOPE, "state": start.raw_state, "code_challenge_method": "S256",
            "code_challenge": challenge(self._verifier),
        }
        return AUTHORIZE + "?" + urlencode(parameters), self._cookie

    def callback(self, path: str, cookie_header: str) -> tuple[int, dict]:
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
        except (CookieError, ValueError, TypeError):
            return 400, {"result": "invalid_browser_binding"}
        supplied = cookie.get(COOKIE)
        if not self._cookie or supplied is None or not hmac.compare_digest(supplied.value.encode(), self._cookie.encode()):
            return 400, {"result": "invalid_browser_binding"}
        callback = handle_callback(path, provider="spotify", callback_path=CALLBACK, authorization=self.authorization, now=self.clock())
        if callback.status != 200:
            return callback.status, {"result": "invalid_or_expired_callback"}
        try:
            if callback.authorization_code is None:
                return 200, {"result": "consent_denied", "local_credentials_erased": True}
            grant = self.transport(TOKEN, form={
                "grant_type": "authorization_code", "client_id": self.client_id,
                "code": callback.authorization_code, "redirect_uri": REDIRECT, "code_verifier": self._verifier,
            })
            _validate_grant(grant)
            refresh = _token(grant.get("refresh_token"))
            profile = self.transport(PROFILE, bearer=grant["access_token"])
            identity = profile.get("id")
            if not isinstance(identity, str) or not identity.strip() or len(identity) > 256:
                raise ProofError("provider_missing_account_identity")
            renewed = self.transport(TOKEN, form={"grant_type": "refresh_token", "refresh_token": refresh, "client_id": self.client_id})
            _validate_grant(renewed, previous_scope=SCOPE)
            if "refresh_token" in renewed:
                _token(renewed["refresh_token"])
            renewed_profile = self.transport(PROFILE, bearer=renewed["access_token"])
            if renewed_profile.get("id") != identity:
                raise ProofError("provider_account_changed")
            return 200, {
                "result": "spotify_pkce_verified", "profile_verified": True, "refresh_verified": True,
                "local_credentials_erased": True, "provider_revocation": "not_run",
                "home_assistant_actor_binding": "not_proven", "remote_app_callback": "not_proven",
            }
        except ProofError as error:
            return 502, {"result": str(error), "local_credentials_erased": True}
        finally:
            self._verifier = ""
            self._cookie = ""
            # No grant is retained on self, in SQLite, on disk, or in HTTP state.


class ResearchServer(RequestDeadlineServer):
    def __init__(self, proof: SpotifyProof, *, address=("127.0.0.1", 8765), parse_seconds=2.0, deadline=None):
        self.proof = proof
        self.report = None
        self.result_viewed = False
        super().__init__(address, ResearchHandler, parse_seconds=parse_seconds, deadline=deadline)
        self.timeout = 1


class ResearchHandler(BaseHTTPRequestHandler):
    server: ResearchServer

    def log_message(self, *args):
        pass

    def _send(self, status: int, body: bytes, *, headers: dict | None = None, content_type="text/html; charset=utf-8"):
        self.send_response(status)
        for key, value in {
            "Content-Type": content_type, "Content-Length": str(len(body)), "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; form-action 'self' https://accounts.spotify.com; frame-ancestors 'none'; base-uri 'none'",
            **(headers or {}),
        }.items():
            self.send_header(key, value)
        try:
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass

    def _valid_host(self):
        return self.headers.get("Host") == "127.0.0.1:8765"

    def do_GET(self):
        self.server.parsing_complete(self.connection)
        if not self._valid_host() or len(self.path) > 12288 or not self.path.startswith("/") or self.path.startswith("//"):
            self._send(400, b"Invalid research request.")
        elif self.path == "/":
            self._send(200, b"<!doctype html><meta charset=utf-8><title>Symphonia Spotify OAuth research</title>"
                       b"<h1>Spotify OAuth research</h1><p>Read-only account verification and one refresh. "
                       b"No playlists, playback, email, or persistent tokens. This is a local PKCE proof, "
                       b"not a Home Assistant connection.</p><form method=post action=/start>"
                       b"<button>Continue to Spotify</button></form>", headers={"Referrer-Policy": "same-origin"})
        elif self.path == "/result" and self.server.report is not None:
            self._send(200, json.dumps(self.server.report).encode(), content_type="application/json")
            self.server.result_viewed = True
        elif urlsplit(self.path).path == CALLBACK:
            status, report = self.server.proof.callback(self.path, self.headers.get("Cookie", ""))
            self.server.report = {"http_status": status, **report}
            self._send(303, b"", headers={"Location": "/result", "Set-Cookie": f"{COOKIE}=; Path={CALLBACK}; Max-Age=0; HttpOnly; SameSite=Lax"})
        else:
            self._send(404, b"Not found.")

    def do_POST(self):
        self.server.parsing_complete(self.connection)
        if not self._valid_host() or self.path != "/start" or self.headers.get("Origin") != ORIGIN or self.headers.get("Content-Length", "0") != "0":
            self._send(400, b"Invalid research request.")
            return
        url, cookie = self.server.proof.begin()
        self._send(303, b"", headers={"Location": url, "Set-Cookie": f"{COOKIE}={cookie}; Path={CALLBACK}; Max-Age=600; HttpOnly; SameSite=Lax"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-id", required=True)
    args = parser.parse_args()
    repository = AuthorizationAttemptRepository()
    server = None
    try:
        deadline = time.monotonic() + 600
        def transport(url, **kwargs):
            return request_json(url, **kwargs, seconds=min(10, deadline - time.monotonic()))
        proof = SpotifyProof(args.client_id, AuthorizationService(repository), transport=transport)
        server = ResearchServer(proof, deadline=deadline)
        print(f"Research page: {ORIGIN}/ (expires in 10 minutes)", flush=True)
        while time.monotonic() < deadline and not server.result_viewed:
            server.timeout = min(1, max(0, deadline - time.monotonic()))
            server.handle_request()
        print(json.dumps(server.report or {"result": "research_timeout"}), flush=True)
        return 0 if server.report and server.report["result"] == "spotify_pkce_verified" else 1
    except (ValueError, OSError):
        print(json.dumps({"result": "research_setup_failed"}), flush=True)
        return 1
    except KeyboardInterrupt:
        return 1
    finally:
        if server is not None:
            server.server_close()
        repository.close()


if __name__ == "__main__":
    raise SystemExit(main())
