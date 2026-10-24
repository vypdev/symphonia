"""Supervisor-only dashboard projection and bounded static asset adapter."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any, Protocol

from symphonia.application.operational_dashboard import project_dashboard


INGRESS_PEER = "172.30.32.2"
ASSET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.(?:js|css|svg)\Z")


class DashboardDiagnosticsPort(Protocol):
    def diagnostics(
        self, *, now: datetime, operation_limit: int, event_limit: int
    ) -> dict[str, Any]: ...


def trusted_ingress_peer(address: str) -> bool:
    """A forwarded header cannot grant access to the UI or dashboard API."""
    return address == INGRESS_PEER


def dashboard_response(
    resources: DashboardDiagnosticsPort | None, *, now: datetime, version: str
) -> tuple[int, dict[str, Any]]:
    """Map a bounded read to a redacted DTO or a closed failure response."""
    if resources is None:
        return 503, {"service": "symphonia", "ready": False}
    try:
        diagnostics = resources.diagnostics(now=now, operation_limit=10, event_limit=1)
        payload = project_dashboard(diagnostics, now=now, version=version)
    except Exception:
        return 503, {"service": "symphonia", "ready": False}
    return (200 if payload["ready"] else 503), payload


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
