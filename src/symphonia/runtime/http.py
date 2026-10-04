"""HTTP health checks and a Supervisor-only operational dashboard."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
import re
from socket import socket
from typing import Any
from urllib.parse import urlsplit

from symphonia import __version__
from symphonia.application.operational_dashboard import project_dashboard
from symphonia.infrastructure.sqlite_operations import OperationRepository
from .config import RuntimeConfig, normalize_ingress_path
from .resources import RuntimeResources


class SymphoniaHTTPServer(HTTPServer):
    allow_reuse_address = True
    request_timeout_seconds = 2.0

    def __init__(
        self,
        address: tuple[str, int],
        repository: OperationRepository | None = None,
        ingress_path: str = "/",
        *,
        resources: RuntimeResources | None = None,
    ) -> None:
        if repository is not None and resources is not None:
            raise ValueError("repository and resources are mutually exclusive")
        if repository is None and resources is None:
            raise ValueError("repository or resources must be supplied")
        normalized_ingress_path = normalize_ingress_path(ingress_path)
        super().__init__(address, SymphoniaRequestHandler)
        self.resources = resources
        self.repository = resources.operations if resources is not None else repository
        self.readiness_check: Callable[[], bool] = resources.healthcheck if resources is not None else repository.healthcheck
        self.service_version = __version__
        self.ingress_path = normalized_ingress_path

    def get_request(self) -> tuple[socket, tuple[str, int]]:
        request, client_address = super().get_request()
        request.settimeout(self.request_timeout_seconds)
        return request, client_address

    def close_resources(self) -> None:
        if self.resources is not None:
            self.resources.close()
            self.resources = None


class SymphoniaRequestHandler(BaseHTTPRequestHandler):
    """Keep the operational UI behind the verified Supervisor proxy peer."""

    server_version = "Symphonia"
    sys_version = ""

    server: SymphoniaHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        relative = _relative_path(self.path, self.server.ingress_path)
        if relative in {"/", "/api/dashboard"} or (
            relative is not None and relative.startswith("/assets/")
        ):
            if not trusted_ingress_peer(self.client_address[0]):
                self._json(403, {"error": "forbidden"})
                return
            if relative == "/api/dashboard":
                self._dashboard()
            else:
                self._asset(relative)
            return
        status, payload = route_get(
            self.path,
            self.server.repository,
            self.server.service_version,
            self.server.ingress_path,
            self.server.readiness_check,
        )
        self._json(status, payload)

    def _dashboard(self) -> None:
        resources = self.server.resources
        if resources is None:
            self._json(503, {"service": "symphonia", "ready": False})
            return
        now = datetime.now(timezone.utc)
        diagnostics = resources.diagnostics(now=now, operation_limit=10, event_limit=1)
        payload = project_dashboard(diagnostics, now=now, version=self.server.service_version)
        self._json(200 if payload["ready"] else 503, payload)

    def _asset(self, relative: str) -> None:
        asset = ui_asset(relative)
        if asset is None:
            self._json(404, {"error": "not_found"})
            return
        content_type, body = asset
        self._send_bytes(200, content_type, body)

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        del message, explain
        error = "not_implemented" if code == 501 else (
            "server_error" if code >= 500 else "bad_request"
        )
        self._json(code, {"error": error}, close_connection=True)

    def version_string(self) -> str:
        return self.server_version

    def _json(
        self,
        status: int,
        payload: dict[str, Any],
        *,
        close_connection: bool = False,
    ) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        SymphoniaRequestHandler._send_bytes(
            self,
            status, "application/json; charset=utf-8", body,
            close_connection=close_connection,
        )

    def _send_bytes(
        self,
        status: int,
        content_type: str,
        body: bytes,
        *,
        close_connection: bool = False,
    ) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'",
            )
            if close_connection:
                self.close_connection = True
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionError, TimeoutError):
            # A client timing out or disconnecting is not a server fault.
            self.close_connection = True

    def log_message(self, format: str, *args: object) -> None:
        # Never log Ingress route tokens, credentials, or request payloads.
        return


INGRESS_PEER = "172.30.32.2"
ASSET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.(?:js|css|svg)\Z")


def trusted_ingress_peer(address: str) -> bool:
    """A forwarded header can never grant access to the UI/API."""
    return address == INGRESS_PEER


def ui_asset(relative: str) -> tuple[str, bytes] | None:
    """Resolve only Vite's single-level, allowlisted output assets."""
    root = Path(__file__).with_name("ui_assets")
    if relative == "/":
        path = root / "index.html"
        content_type = "text/html; charset=utf-8"
    elif relative.startswith("/assets/"):
        name = relative[len("/assets/"):]
        if not ASSET_NAME.fullmatch(name):
            return None
        path = root / "assets" / name
        content_type = {
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
        }[path.suffix]
    else:
        return None
    try:
        if not path.is_file() or path.stat().st_size > 2_000_000:
            return None
        return content_type, path.read_bytes()
    except OSError:
        return None

def create_server(
    host: str = "127.0.0.1",
    port: int = 8099,
    database_path: str = ":memory:",
    ingress_path: str = "/",
) -> SymphoniaHTTPServer:
    """Create a server with an already-migrated durable operation store."""

    config = RuntimeConfig(
        host=host,
        port=port,
        database_path=database_path,
        ingress_path=ingress_path,
    )
    resources = RuntimeResources.open(config.database_path)
    try:
        return SymphoniaHTTPServer(
            (config.host, config.port),
            ingress_path=config.ingress_path,
            resources=resources,
        )
    except BaseException as startup_error:
        try:
            resources.close()
        except BaseException as cleanup_error:
            startup_error.add_note(
                "runtime resource cleanup also failed "
                f"({type(cleanup_error).__name__})"
            )
        raise


def route_get(
    path: str,
    repository: OperationRepository,
    service_version: str = __version__,
    ingress_path: str = "/",
    readiness_check: Callable[[], bool] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Resolve a GET request without opening a socket.

    Keeping this decision pure-ish makes health/readiness contract tests work
    in restricted CI environments and prevents a network permission from being
    mistaken for application readiness.
    """

    relative_path = _relative_path(path, normalize_ingress_path(ingress_path))
    if relative_path is None:
        return 404, {"error": "not_found"}
    if relative_path == "/health":
        return 200, {"service": "symphonia", "status": "ok", "version": service_version}
    if relative_path == "/ready":
        try:
            healthy = (readiness_check or repository.healthcheck)()
        except Exception:  # readiness must fail closed without exposing internals
            healthy = False
        return (200, {"service": "symphonia", "status": "ready"}) if healthy else (
            503,
            {"service": "symphonia", "status": "not_ready"},
        )
    if relative_path == "/version":
        return 200, {"service": "symphonia", "version": service_version}
    return 404, {"error": "not_found"}


def _relative_path(request_path: str, base_path: str) -> str | None:
    if (
        not isinstance(request_path, str)
        or not request_path.startswith("/")
        or request_path.startswith("//")
    ):
        return None
    try:
        parsed = urlsplit(request_path)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return None
    path = parsed.path or "/"
    if base_path == "/":
        return path
    if path == base_path:
        return "/"
    prefix = f"{base_path}/"
    if path.startswith(prefix):
        return path[len(base_path):] or "/"
    return None
