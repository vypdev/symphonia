"""Pure health/readiness route selection under a normalized Ingress prefix."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from urllib.parse import urlsplit

from symphonia import __version__

from .config import normalize_ingress_path


class HealthcheckPort(Protocol):
    def healthcheck(self) -> bool: ...


def route_get(
    path: str,
    repository: HealthcheckPort,
    service_version: str = __version__,
    ingress_path: str = "/",
    readiness_check: Callable[[], bool] | None = None,
) -> tuple[int, dict[str, str]]:
    """Resolve public probes without sockets or persistence-adapter imports."""

    relative = relative_path(path, normalize_ingress_path(ingress_path))
    if relative is None:
        return 404, {"error": "not_found"}
    if relative == "/health":
        return 200, {"service": "symphonia", "status": "ok", "version": service_version}
    if relative == "/ready":
        try:
            healthy = (readiness_check or repository.healthcheck)()
        except Exception:
            healthy = False
        return (200, {"service": "symphonia", "status": "ready"}) if healthy else (
            503, {"service": "symphonia", "status": "not_ready"}
        )
    if relative == "/version":
        return 200, {"service": "symphonia", "version": service_version}
    return 404, {"error": "not_found"}


def relative_path(request_path: str, base_path: str) -> str | None:
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
