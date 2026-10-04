"""Classify Spotify HTTP failures without copying provider response bodies."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from .errors import ProviderApiError, ProviderErrorCategory
from .http_json import JsonResponse
from .writing import WriteOutcome


def classify_response(response: JsonResponse) -> ProviderApiError:
    category = {
        401: ProviderErrorCategory.AUTHENTICATION_REQUIRED,
        403: ProviderErrorCategory.PERMISSION_DENIED,
        404: ProviderErrorCategory.NOT_FOUND,
        429: ProviderErrorCategory.RATE_LIMITED,
    }.get(
        response.status,
        ProviderErrorCategory.PROVIDER_UNAVAILABLE
        if response.status >= 500 else ProviderErrorCategory.INVALID_REQUEST,
    )
    retry_at = None
    retry_after = _header(response.headers, "retry-after")
    if category is ProviderErrorCategory.RATE_LIMITED and retry_after is not None:
        try:
            retry_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, int(retry_after)))
        except ValueError:
            retry_at = None
    error_body = response.payload.get("error") if isinstance(response.payload, Mapping) else None
    provider_code = (
        str(error_body.get("status"))
        if isinstance(error_body, Mapping) and error_body.get("status") is not None
        else str(response.status)
    )
    return ProviderApiError(
        category, "Spotify API request was not accepted",
        provider_code=provider_code, retry_at=retry_at,
    )


def write_outcome(error: ProviderApiError) -> WriteOutcome:
    if error.category is ProviderErrorCategory.RATE_LIMITED:
        return WriteOutcome.RATE_LIMITED
    if error.category in {
        ProviderErrorCategory.TIMEOUT,
        ProviderErrorCategory.NETWORK_ERROR,
        ProviderErrorCategory.PROVIDER_UNAVAILABLE,
        ProviderErrorCategory.UNKNOWN_WRITE_OUTCOME,
    }:
        return WriteOutcome.UNKNOWN_OUTCOME
    return WriteOutcome.PERMANENT_FAILURE


def _header(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.lower()
    return next((value for key, value in headers.items() if key.lower() == wanted), None)
