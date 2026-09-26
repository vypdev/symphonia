"""Dependency-free HTTP health surface for the first runtime slice."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from collections.abc import Callable
from socket import socket
from typing import Any
from urllib.parse import urlsplit

from symphonia import __version__
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
    """Only health/readiness/version are exposed until the API SDD is ready."""

    server_version = "Symphonia"
    sys_version = ""

    server: SymphoniaHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        status, payload = route_get(
            self.path,
            self.server.repository,
            self.server.service_version,
            self.server.ingress_path,
            self.server.readiness_check,
        )
        self._json(status, payload)

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
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if close_connection:
                self.close_connection = True
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionError, TimeoutError):
            # A client timing out or disconnecting is not a server fault.
            self.close_connection = True

    def log_message(self, format: str, *args: object) -> None:
        # Keep the first runtime quiet; structured logging belongs to the
        # observability adapter and must not include request payloads by default.
        return


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
