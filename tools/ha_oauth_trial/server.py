"""Disposable HA research App. No durable grants, HA API access or production code."""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import hmac
import html
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


CALLBACK = "/oauth/callback"
TOKEN = "https://accounts.spotify.com/api/token"
PROFILE = "https://api.spotify.com/v1/me"
AUTHORIZE = "https://accounts.spotify.com/authorize"
SCOPE = "user-read-private"
COOKIE = "symphonia_oauth_trial"
RUN_SECONDS = 1200
FLOW_SECONDS = 600
TUNNEL_HOST = re.compile(r"https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com\Z")


class Rejected(Exception):
    """Fixed safe result, never provider response text."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_json(url, *, form=None, bearer=None):
    if url not in {TOKEN, PROFILE}:
        raise Rejected("unsupported_endpoint")
    headers = {"Accept": "application/json"}
    data = None
    if form is not None:
        data = urlencode(form).encode("ascii")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if bearer is not None:
        headers["Authorization"] = "Bearer " + valid_token(bearer)
    try:
        with build_opener(ProxyHandler({}), NoRedirect).open(Request(url, data=data, headers=headers), timeout=10) as response:
            body = response.read(65537)
    except HTTPError as error:
        error.close()
        raise Rejected("provider_http_error") from None
    except (URLError, OSError, TimeoutError):
        raise Rejected("provider_unreachable") from None
    if len(body) > 65536:
        raise Rejected("provider_response_too_large")
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError):
        raise Rejected("provider_invalid_json") from None
    if not isinstance(value, dict):
        raise Rejected("provider_invalid_object")
    return value


def valid_token(value):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9._~+/-]{1,8192}={0,2}", value) is None:
        raise Rejected("provider_invalid_token")
    return value


def validate_grant(value, *, refresh=False):
    if not isinstance(value, dict) or (
        not isinstance(value.get("token_type"), str) or value["token_type"].lower() != "bearer"
        or type(value.get("expires_in")) is not int or value["expires_in"] <= 0
    ):
        raise Rejected("provider_invalid_grant")
    scope = value.get("scope", SCOPE if refresh else None)
    if not isinstance(scope, str) or set(scope.split()) != {SCOPE}:
        raise Rejected("provider_unexpected_scopes")
    valid_token(value.get("access_token"))
    if not refresh or "refresh_token" in value:
        valid_token(value.get("refresh_token"))


def verify_spotify(client_id, code, verifier, redirect, transport=request_json):
    grant = transport(TOKEN, form={"grant_type": "authorization_code", "client_id": client_id,
        "code": code, "code_verifier": verifier, "redirect_uri": redirect})
    validate_grant(grant)
    profile = transport(PROFILE, bearer=grant["access_token"])
    identity = profile.get("id")
    if not isinstance(identity, str) or not identity.strip() or len(identity) > 256:
        raise Rejected("provider_missing_identity")
    renewed = transport(TOKEN, form={"grant_type": "refresh_token", "client_id": client_id,
        "refresh_token": grant["refresh_token"]})
    validate_grant(renewed, refresh=True)
    if transport(PROFILE, bearer=renewed["access_token"]).get("id") != identity:
        raise Rejected("provider_account_changed")
    # No response or reusable grant is retained on any service object.


def configuration(value):
    if not isinstance(value, dict) or set(value) != {"client_id", "management_origin", "tunnel_enabled"}:
        raise ValueError("invalid_options")
    client, origin = value["client_id"], value["management_origin"]
    if not isinstance(client, str) or re.fullmatch(r"[a-f0-9]{32}", client) is None:
        raise ValueError("invalid_client_id")
    if not isinstance(origin, str) or re.fullmatch(r"https://[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?", origin) is None:
        raise ValueError("management_requires_https_origin")
    parsed = urlsplit(origin)
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("invalid_management_port")
    if type(value["tunnel_enabled"]) is not bool:
        raise ValueError("invalid_tunnel_option")
    return value.copy()


def read_options(path=Path("/data/options.json")):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 4096:
            raise ValueError("invalid_options_file")
        body = source.read(4097)
    if len(body) > 4096:
        raise ValueError("options_too_large")
    return json.loads(body)


def drop_privileges():
    # Never hand Supervisor credentials or an inherited proxy environment to
    # provider requests or the tunnel. No credential value is inspected.
    os.environ.clear()
    os.environ.update({"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp"})
    os.umask(0o077)
    if os.getuid() == 0:
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    if os.geteuid() != 10001:
        raise ValueError("trial_requires_unprivileged_uid")


def one_cookie(header, name):
    if not isinstance(header, str) or len(re.findall(r"(?:^|;)\s*" + re.escape(name) + "=", header)) != 1:
        raise Rejected("invalid_session")
    cookies = SimpleCookie()
    try:
        cookies.load(header)
    except (CookieError, ValueError):
        raise Rejected("invalid_session") from None
    if name not in cookies:
        raise Rejected("invalid_session")
    return cookies[name].value


@dataclass(frozen=True)
class IngressIdentity:
    actor: str = field(repr=False)
    session: bytes = field(repr=False)
    base_path: str = field(repr=False)


class Trial:
    def __init__(self, options, *, clock=time.monotonic, exchange=verify_spotify):
        self.options = configuration(options)
        self.clock, self.exchange = clock, exchange
        self.key = secrets.token_bytes(32)
        self.started = clock()
        self.lock = threading.RLock()
        self.callback_origin = ""
        self.sessions = {}
        self.flow = None
        self.used = False
        self.report = {"result": "tunnel_disabled" if not options["tunnel_enabled"] else "waiting_for_https"}

    def digest(self, value):
        return hmac.digest(self.key, value.encode(), "sha256")

    def identity(self, peer, headers):
        # Only the actual socket peer grants meaning to forwarded identity.
        if peer != "172.30.32.2" or headers.get_all("X-Remote-User-Id", []) == []:
            raise Rejected("trusted_ingress_required")
        users = headers.get_all("X-Remote-User-Id", [])
        cookies = headers.get_all("Cookie", [])
        paths = headers.get_all("X-Ingress-Path", [])
        if len(users) != 1 or re.fullmatch(r"[a-f0-9]{32}", users[0]) is None:
            raise Rejected("invalid_actor")
        if len(paths) != 1 or re.fullmatch(r"/api/hassio_ingress/[A-Za-z0-9_-]{1,256}", paths[0]) is None:
            raise Rejected("invalid_ingress_path")
        if headers.get_all("X-Forwarded-Proto", []) != ["https"]:
            raise Rejected("open_home_assistant_over_https")
        if len(cookies) != 1:
            raise Rejected("invalid_session")
        session = one_cookie(cookies[0], "ingress_session")
        if re.fullmatch(r"[a-f0-9]{128}", session) is None:
            raise Rejected("invalid_session")
        return IngressIdentity(users[0], self.digest(session), paths[0])

    def set_callback_origin(self, origin):
        with self.lock:
            if not isinstance(origin, str) or TUNNEL_HOST.fullmatch(origin) is None or self.callback_origin:
                raise Rejected("invalid_or_changed_tunnel")
            self.callback_origin = origin
            self.report = {"result": "register_callback_then_start"}

    def expire(self):
        with self.lock:
            if self.flow and self.clock() >= self.flow["deadline"]:
                self.flow = None
                self.report = {"result": "attempt_expired", "local_credentials_erased": True}
            if self.clock() >= self.started + RUN_SECONDS:
                self.flow = None
                self.sessions.clear()
                return True
            return False

    def browser(self, identity, cookie_header, *, create=False):
        with self.lock:
            if self.expire():
                raise Rejected("trial_expired")
            nonce = ""
            try:
                nonce = one_cookie(cookie_header, COOKIE)
            except Rejected:
                if not create:
                    raise
            session = self.sessions.get(self.digest(nonce)) if nonce else None
            if session is not None:
                if session["identity"] != identity:
                    raise Rejected("initiating_ingress_session_required")
                return nonce, session["csrf"]
            if not create or len(self.sessions) >= 8:
                raise Rejected("invalid_browser_session")
            nonce, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self.sessions[self.digest(nonce)] = {"identity": identity, "csrf": csrf}
            return nonce, csrf

    def post(self, action, identity, cookie_header, origin, csrf):
        with self.lock:
            nonce, expected = self.browser(identity, cookie_header)
            if origin != self.options["management_origin"] or not isinstance(csrf, str) or not hmac.compare_digest(expected.encode(), csrf.encode()):
                raise Rejected("invalid_request_origin_or_csrf")
            if action == "/start":
                if not self.callback_origin or self.used:
                    raise Rejected("callback_unavailable_or_trial_already_used")
                self.used = True
                state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
                redirect = self.callback_origin + CALLBACK
                self.flow = {"state": self.digest(state), "verifier": verifier, "redirect": redirect,
                    "browser": self.digest(nonce), "identity": identity,
                    "deadline": self.clock() + FLOW_SECONDS, "pending": None}
                self.report = {"result": "waiting_for_spotify"}
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
                return AUTHORIZE + "?" + urlencode({"client_id": self.options["client_id"], "response_type": "code",
                    "redirect_uri": redirect, "state": state, "scope": SCOPE,
                    "code_challenge_method": "S256", "code_challenge": challenge})
            if action not in {"/complete", "/cancel"}:
                raise Rejected("unsupported_action")
            if not self.flow or self.flow["identity"] != identity or not hmac.compare_digest(self.flow["browser"], self.digest(nonce)):
                raise Rejected("initiating_browser_required")
            if action == "/cancel":
                self.flow = None
                self.report = {"result": "cancelled", "local_credentials_erased": True}
                return None
            if self.flow["pending"] is None:
                raise Rejected("callback_not_received")
            flow, self.flow = self.flow, None  # one owner before provider I/O
            try:
                code = flow["pending"]
                if code is False:
                    self.report = {"result": "consent_denied", "local_credentials_erased": True}
                else:
                    self.exchange(self.options["client_id"], code, flow["verifier"], flow["redirect"])
                    self.report = {"result": "spotify_pkce_verified", "profile_verified": True, "refresh_verified": True,
                        "ha_actor_bound": True, "ingress_session_bound": True, "app_browser_session_bound": True,
                        "app_callback_received": True, "local_credentials_erased": True,
                        "core_login_revocation": "not_proven", "provider_revocation": "not_run"}
            except Exception:
                self.report = {"result": "provider_verification_failed", "local_credentials_erased": True}
            finally:
                flow.clear()
            return None

    def receive(self, path, host):
        with self.lock:
            self.expire()
            if not self.callback_origin or host != urlsplit(self.callback_origin).netloc:
                raise Rejected("invalid_callback_host")
            if not isinstance(path, str) or len(path) > 12288 or not path.startswith("/") or path.startswith("//"):
                raise Rejected("invalid_callback")
            parsed = urlsplit(path)
            if parsed.path != CALLBACK or parsed.fragment:
                raise Rejected("callback_route_only")
            try:
                query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=8)
            except ValueError:
                raise Rejected("invalid_callback") from None
            for name in ("state", "code", "error"):
                if name in query and (len(query[name]) != 1 or not query[name][0].strip() or len(query[name][0]) > (8192 if name == "code" else 512)):
                    raise Rejected("invalid_callback")
            if "state" not in query or ("code" in query) == ("error" in query) or not self.flow:
                raise Rejected("invalid_callback")
            if not hmac.compare_digest(self.digest(query["state"][0]), self.flow["state"]) or self.flow["pending"] is not None:
                raise Rejected("invalid_or_duplicate_callback")
            self.flow["pending"] = False if "error" in query else query["code"][0]
            self.report = {"result": "return_to_ha_and_complete"}


class TrialServer(HTTPServer):
    def __init__(self, address, trial, *, callback=False):
        self.trial, self.callback = trial, callback
        super().__init__(address, TrialHandler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(2)
        return connection, address


class TrialHandler(BaseHTTPRequestHandler):
    server_version = "SymphoniaTrial"
    sys_version = ""

    def log_message(self, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self.send(400, b"Invalid trial request.")

    def send(self, status, body, *, headers=None):
        self.send_response(status)
        for name, value in {"Content-Type": "text/html; charset=utf-8", "Content-Length": str(len(body)),
            "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; form-action 'self' https://accounts.spotify.com; frame-ancestors 'self'; base-uri 'none'",
            "Connection": "close", **(headers or {})}.items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (OSError, TimeoutError):
            pass
        self.close_connection = True

    def ingress(self):
        return self.server.trial.identity(self.client_address[0], self.headers)

    def do_GET(self):
        trial = self.server.trial
        if self.server.callback:
            try:
                hosts = self.headers.get_all("Host", [])
                trial.receive(self.path, hosts[0] if len(hosts) == 1 else "")
                self.send(200, b"<!doctype html><meta charset=utf-8><title>Symphonia OAuth Trial</title>"
                    b"<h1>Callback recibido</h1><p>Regresa a tu pestana de Home Assistant y pulsa Completar. "
                    b"El callback no ha canjeado credenciales.</p>", headers={"Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'"})
            except (Rejected, ValueError):
                self.send(400, b"Invalid, expired or unavailable callback.")
            return
        if self.path == "/health":
            self.send(200, b"trial_running")
            return
        try:
            identity = self.ingress()
            if self.path != "/":
                raise Rejected("unsupported_route")
            cookie_header = self.headers.get("Cookie", "")
            nonce, csrf = trial.browser(identity, cookie_header, create=True)
            with trial.lock:
                callback = trial.callback_origin + CALLBACK if trial.callback_origin else "Tunnel disabled or waiting"
                status = json.dumps(trial.report, sort_keys=True)
            # Core replaces the response Referrer-Policy with no-referrer.
            # Set the private document policy too: same-origin POSTs keep their
            # Origin while cross-origin consent requests get no Referer.
            body = "<!doctype html><meta charset=utf-8><meta name=referrer content=same-origin><title>Symphonia OAuth Trial</title><h1>Symphonia OAuth Trial</h1>"
            body += "<p>Prueba temporal: solo lectura de perfil y una renovacion. Sin biblioteca, reproduccion ni tokens persistentes. Se detiene a los 20 minutos.</p>"
            body += "<p>Registra esta URI exacta en la app de prueba de Spotify:</p><pre>" + html.escape(callback) + "</pre>"
            body += "<pre>" + html.escape(status) + "</pre><a href='./'>Actualizar estado</a>"
            body += "<p>Research server SHA-256:</p><pre>" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest() + "</pre>"
            for action, label in (("start", "Autorizar Spotify"), ("complete", "Completar"), ("cancel", "Cancelar")):
                target = " target='_blank'" if action == "start" else ""
                body += f"<form method=post action='./{action}'{target}><input type=hidden name=csrf value='{csrf}'><button>{label}</button></form>"
            self.send(200, body.encode(), headers={"Referrer-Policy": "same-origin", "Set-Cookie":
                f"{COOKIE}={nonce}; Path={identity.base_path}/; Max-Age={RUN_SECONDS}; HttpOnly; Secure; SameSite=Strict"})
        except (Rejected, ValueError):
            self.send(403, b"Open this admin-only App through Home Assistant HTTPS Ingress.")

    def do_POST(self):
        if self.server.callback:
            self.send(404, b"Not found.")
            return
        try:
            identity = self.ingress()
            if self.path not in {"/start", "/complete", "/cancel"} or self.headers.get("Content-Type") != "application/x-www-form-urlencoded":
                raise Rejected("unsupported_request")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= 256 or self.headers.get("Transfer-Encoding"):
                raise Rejected("invalid_request_size")
            body = self.rfile.read(int(lengths[0])).decode("ascii")
            data = parse_qs(body, keep_blank_values=True, max_num_fields=1)
            if set(data) != {"csrf"} or len(data["csrf"]) != 1 or len(self.headers.get_all("Origin", [])) != 1:
                raise Rejected("invalid_form")
            target = self.server.trial.post(self.path, identity, self.headers.get("Cookie", ""), self.headers["Origin"], data["csrf"][0])
            self.send(303, b"", headers={"Location": target or identity.base_path + "/"})
        except (Rejected, ValueError, UnicodeError, OSError):
            self.send(403, b"Trial action rejected. Refresh the App or start a new trial.")


def tunnel_command():
    return ["/usr/local/bin/cloudflared", "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8100",
        "--protocol", "http2", "--metrics", "127.0.0.1:20241", "--loglevel", "info"]


def capture_tunnel(process, trial):
    # Read but never forward or persist raw cloudflared log lines.
    for line in process.stderr:
        matches = re.findall(r"https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com", line)
        if matches and not trial.callback_origin:
            try:
                trial.set_callback_origin(matches[0])
                print('{"tunnel":"callback_only_ready"}', flush=True)
            except Rejected:
                pass


def main():
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *args: stop.set())
    servers, process, trial = [], None, None
    try:
        options = read_options()
        drop_privileges()
        trial = Trial(options)
        for address, callback in ((("127.0.0.1", 8100), True), (("0.0.0.0", 8099), False)):
            server = TrialServer(address, trial, callback=callback)
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        if trial.options["tunnel_enabled"]:
            process = subprocess.Popen(tunnel_command(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True, env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp"})
            threading.Thread(target=capture_tunnel, args=(process, trial), daemon=True).start()
        print('{"trial":"started","limit_seconds":1200,"service_uid":10001}', flush=True)
        while not stop.wait(1) and not trial.expire():
            if process is not None and process.poll() is not None:
                print('{"trial":"tunnel_stopped"}', flush=True)
                break
        return 0
    except Exception:
        print('{"trial":"setup_failed"}', flush=True)
        return 1
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for server in reversed(servers):
            server.shutdown()
            server.server_close()
        if trial is not None:
            trial.flow = None
            trial.sessions.clear()
        print('{"trial":"stopped","local_credentials_erased":true}', flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
