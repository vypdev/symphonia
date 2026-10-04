"""Probe the disposable App's Supervisor Ingress route from Home Assistant Core.

This file is passed as source to ``python3 -c`` inside the local Core container.
It uses Core's existing Supervisor token and never prints it, the Ingress URL,
the route token, or the newly created session cookie.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit


SUPERVISOR = "http://supervisor"
TOKEN = re.compile(r"[A-Za-z0-9_-]+\Z")
Response = tuple[int, bytes]
Requester = Callable[[str, str, bytes | None, str | None], Response]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep Supervisor credentials and session cookies on the internal host."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def proxy_path(ingress_url: object, endpoint: str) -> str:
    """Select a fixed diagnostic route from a Supervisor-provided relative URL."""
    if not isinstance(ingress_url, str) or endpoint not in {"", "health", "ready"}:
        raise ValueError("invalid Ingress probe route")
    parsed = urlsplit(ingress_url)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Ingress URL must be a relative path")
    parts = parsed.path.split("/")
    if parts[:3] != ["", "api", "hassio_ingress"] or len(parts) < 4:
        raise ValueError("unexpected Ingress URL prefix")
    route_token = parts[3]
    if not TOKEN.fullmatch(route_token):
        raise ValueError("invalid Ingress route token")
    return f"/ingress/{route_token}/{endpoint}"


def probe(request: Requester) -> dict[str, object]:
    """Verify session enforcement, upstream routing, and current UI absence."""
    session_status, session_body = request("/ingress/session", "POST", b"{}", None)
    if session_status != 200:
        raise RuntimeError("Supervisor did not create an Ingress session")
    session = json.loads(session_body)["data"]["session"]
    if not isinstance(session, str) or not session:
        raise ValueError("Supervisor returned an invalid Ingress session")

    info_status, info_body = request("/addons/local_symphonia/info", "GET", None, None)
    if info_status != 200:
        raise RuntimeError("Supervisor did not return local App information")
    info = json.loads(info_body)["data"]
    if info.get("state") != "started":
        raise RuntimeError("Symphonia App is not started")
    ingress_url = info["ingress_url"]

    health_path = proxy_path(ingress_url, "health")
    denied_status, _ = request(health_path, "GET", None, None)
    health_status, health_body = request(health_path, "GET", None, session)
    ready_status, ready_body = request(proxy_path(ingress_url, "ready"), "GET", None, session)
    root_status, _ = request(proxy_path(ingress_url, ""), "GET", None, session)
    health = json.loads(health_body) if health_status == 200 else {}
    ready = json.loads(ready_body) if ready_status == 200 else {}
    result = {
        "app_state": "started",
        "without_session": denied_status,
        "health": health_status,
        "ready": ready_status,
        "root": root_status,
        "health_service": health.get("service"),
        "ready_state": ready.get("status"),
    }
    if result != {
        "app_state": "started",
        "without_session": 401,
        "health": 200,
        "ready": 200,
        "root": 404,
        "health_service": "symphonia",
        "ready_state": "ready",
    }:
        raise RuntimeError(f"Ingress smoke failed: {result}")
    return result


def supervisor_request(path: str, method: str, data: bytes | None, session: str | None) -> Response:
    """Use only the Core-to-Supervisor network and bounded HTTP responses."""
    headers = {"Authorization": "Bearer " + os.environ["SUPERVISOR_TOKEN"]}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if session is not None:
        headers["Cookie"] = "ingress_session=" + session
    request = urllib.request.Request(SUPERVISOR + path, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
    try:
        with opener.open(request, timeout=8) as response:
            return response.status, response.read(4096)
    except urllib.error.HTTPError as error:
        return error.code, error.read(4096)


def main() -> int:
    try:
        result = probe(supervisor_request)
    except (KeyError, ValueError, RuntimeError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
        # Do not stringify exceptions: urllib may include a secret-bearing URL.
        print(json.dumps({"error": type(error).__name__}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
