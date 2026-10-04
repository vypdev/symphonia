"""Callback-only OAuth boundary spike for the direct App flow.

This module deliberately lives under ``tools`` until the authorization SDD is
ready for production implementation. It proves route isolation, durable
state consumption, provider binding, and secret-safe callback responses using
only the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlsplit

from symphonia.application.authorization import AuthorizationService
from symphonia.infrastructure.sqlite_authorization import (
    AuthorizationAttemptError,
    AuthorizationAttemptNotFound,
)
from symphonia.providers.authorization import AuthorizationAttempt


@dataclass(frozen=True, slots=True)
class OAuthCallbackResult:
    """Safe HTTP result plus transient handoff data for the exchange owner."""

    status: int
    message: str
    attempt: AuthorizationAttempt | None = None
    authorization_code: str | None = field(default=None, repr=False)


def handle_callback(
    request_path: str,
    *,
    provider: str,
    callback_path: str,
    authorization: AuthorizationService,
    now: datetime,
) -> OAuthCallbackResult:
    """Handle only one provider callback path without echoing query values."""

    if not provider.strip():
        raise ValueError("provider must not be blank")
    callback_path = _normalize_callback_path(callback_path)
    parsed = urlsplit(request_path)
    if parsed.path != callback_path or parsed.fragment:
        return OAuthCallbackResult(404, "Not found.")

    query = parse_qs(parsed.query, keep_blank_values=True)
    try:
        state = _single_query_value(query, "state")
        error = _single_query_value(query, "error")
        code = _single_query_value(query, "code", max_length=8192)
    except ValueError:
        return OAuthCallbackResult(400, "The authorization callback is invalid or expired.")
    if state is None:
        return OAuthCallbackResult(400, "The authorization callback is invalid or expired.")

    if error is not None and code is not None:
        return OAuthCallbackResult(400, "The authorization callback is invalid or expired.")

    try:
        if error is not None:
            attempt = authorization.deny_callback(
                raw_state=state,
                provider=provider,
                now=now,
                failure_code="provider_consent_denied",
            )
            return OAuthCallbackResult(200, "Authorization was cancelled. You can close this window.", attempt=attempt)
        if code is None:
            return OAuthCallbackResult(400, "The authorization callback is invalid or expired.")
        attempt = authorization.consume_callback_for_provider(
            raw_state=state,
            provider=provider,
            now=now,
        )
    except (AuthorizationAttemptError, AuthorizationAttemptNotFound, ValueError):
        return OAuthCallbackResult(400, "The authorization callback is invalid or expired.")

    return OAuthCallbackResult(
        200,
        "Authorization received. You can close this window.",
        attempt=attempt,
        authorization_code=code,
    )


class CallbackOnlyServer(HTTPServer):
    """A spike server exposing exactly one callback route."""

    def __init__(
        self,
        address: tuple[str, int],
        *,
        provider: str,
        callback_path: str,
        authorization: AuthorizationService,
        clock: Any,
    ) -> None:
        self.provider = provider
        self.callback_path = _normalize_callback_path(callback_path)
        self.authorization = authorization
        self.clock = clock
        super().__init__(address, CallbackOnlyRequestHandler)


class CallbackOnlyRequestHandler(BaseHTTPRequestHandler):
    server: CallbackOnlyServer

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        result = handle_callback(
            self.path,
            provider=self.server.provider,
            callback_path=self.server.callback_path,
            authorization=self.server.authorization,
            now=self.server.clock(),
        )
        body = result.message.encode("utf-8")
        self.send_response(result.status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def create_callback_server(
    *,
    authorization: AuthorizationService,
    provider: str,
    callback_path: str = "/oauth/callback",
    host: str = "127.0.0.1",
    port: int = 0,
    clock: Any,
) -> CallbackOnlyServer:
    """Create a loopback-only spike server; no accidental public bind."""

    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("the callback spike only permits a loopback host")
    return CallbackOnlyServer(
        (host, port),
        provider=provider,
        callback_path=callback_path,
        authorization=authorization,
        clock=clock,
    )


def _normalize_callback_path(value: str) -> str:
    if not value or not value.startswith("/") or "?" in value or "#" in value:
        raise ValueError("callback_path must be an absolute path without query or fragment")
    normalized = value.rstrip("/") or "/"
    if "//" in normalized or "/../" in normalized or normalized.endswith("/.."):
        raise ValueError("callback_path contains an unsafe segment")
    return normalized


def _single_query_value(query: Mapping[str, list[str]], name: str, *, max_length: int = 512) -> str | None:
    values = query.get(name)
    if values is None:
        return None
    if len(values) != 1 or not values[0].strip() or len(values[0]) > max_length:
        raise ValueError(f"callback query parameter {name} is invalid")
    return values[0]
