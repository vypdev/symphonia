"""Dependency-free HTTP health surface for the first runtime slice."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from symphonia import __version__
from symphonia.infrastructure.sqlite_operations import OperationRepository
from .resources import RuntimeResources


class SymphoniaHTTPServer(HTTPServer):
    allow_reuse_address = True

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
        normalized_ingress_path = _normalize_base_path(ingress_path)
        super().__init__(address, SymphoniaRequestHandler)
        self.resources = resources
        self.repository = resources.operations if resources is not None else repository
        self.readiness_check: Callable[[], bool] = resources.healthcheck if resources is not None else repository.healthcheck
        self.service_version = __version__
        self.ingress_path = normalized_ingress_path

    def close_resources(self) -> None:
        if self.resources is not None:
            self.resources.close()
            self.resources = None


class SymphoniaRequestHandler(BaseHTTPRequestHandler):
    """Only health/readiness/version are exposed until the API SDD is ready."""

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

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

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

    resources = RuntimeResources.open(database_path)
    try:
        return SymphoniaHTTPServer((host, port), ingress_path=ingress_path, resources=resources)
    except Exception:
        resources.close()
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

    relative_path = _relative_path(path, _normalize_base_path(ingress_path))
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


def _normalize_base_path(value: str) -> str:
    if not value or not value.startswith("/"):
        raise ValueError("ingress path must start with '/'")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError("ingress path must not contain control characters")
    if "?" in value or "#" in value:
        raise ValueError("ingress path must contain only a path")
    normalized = value.rstrip("/") or "/"
    if "//" in normalized or "/.." in normalized or "/./" in normalized:
        raise ValueError("ingress path contains an unsafe segment")
    return normalized


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
