"""Dependency-free HTTP health surface for the first runtime slice."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from typing import Any

from symphonia import __version__
from symphonia.infrastructure.sqlite_operations import OperationRepository


class SymphoniaHTTPServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], repository: OperationRepository) -> None:
        super().__init__(address, SymphoniaRequestHandler)
        self.repository = repository
        self.service_version = __version__


class SymphoniaRequestHandler(BaseHTTPRequestHandler):
    """Only health/readiness/version are exposed until the API SDD is ready."""

    server: SymphoniaHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        status, payload = route_get(self.path, self.server.repository, self.server.service_version)
        self._json(status, payload)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Keep the first runtime quiet; structured logging belongs to the
        # observability adapter and must not include request payloads by default.
        return


def create_server(host: str = "127.0.0.1", port: int = 8099, database_path: str = ":memory:") -> SymphoniaHTTPServer:
    """Create a server with an already-migrated durable operation store."""

    repository = OperationRepository(database_path)
    return SymphoniaHTTPServer((host, port), repository)


def route_get(path: str, repository: OperationRepository, service_version: str = __version__) -> tuple[int, dict[str, Any]]:
    """Resolve a GET request without opening a socket.

    Keeping this decision pure-ish makes health/readiness contract tests work
    in restricted CI environments and prevents a network permission from being
    mistaken for application readiness.
    """

    if path == "/health":
        return 200, {"service": "symphonia", "status": "ok", "version": service_version}
    if path == "/ready":
        try:
            healthy = repository.healthcheck()
        except Exception:  # readiness must fail closed without exposing internals
            healthy = False
        return (200, {"service": "symphonia", "status": "ready"}) if healthy else (
            503,
            {"service": "symphonia", "status": "not_ready"},
        )
    if path == "/version":
        return 200, {"service": "symphonia", "version": service_version}
    return 404, {"error": "not_found"}
