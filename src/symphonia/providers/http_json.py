"""Provider-neutral JSON HTTP transport shared by official adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .errors import ProviderApiError, ProviderErrorCategory


@dataclass(frozen=True, slots=True)
class JsonResponse:
    status: int
    payload: Mapping[str, Any]
    headers: Mapping[str, str]


class JsonClient(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        query: Mapping[str, str],
        body: Mapping[str, Any] | None = None,
    ) -> JsonResponse: ...


class UrllibJsonClient:
    """Bounded JSON transport; the default endpoint preserves Spotify callers."""

    def __init__(
        self,
        base_url: str = "https://api.spotify.com/v1",
        timeout_seconds: float = 10.0,
        provider_label: str = "Spotify",
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not isinstance(provider_label, str) or not provider_label.strip():
            raise ValueError("provider_label must be non-empty text")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.provider_label = provider_label

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        query: Mapping[str, str],
        body: Mapping[str, Any] | None = None,
    ) -> JsonResponse:
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query)}"
        encoded_body = None if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
        }
        request = Request(url, data=encoded_body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read()
                payload = json.loads(body.decode("utf-8")) if body else {}
                return JsonResponse(response.status, payload, dict(response.headers.items()))
        except HTTPError as error:
            body = error.read()
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = {}
            return JsonResponse(error.code, payload, dict(error.headers.items()))
        except TimeoutError as error:
            raise ProviderApiError(ProviderErrorCategory.TIMEOUT, f"{self.provider_label} request timed out") from error
        except URLError as error:
            raise ProviderApiError(ProviderErrorCategory.NETWORK_ERROR, f"{self.provider_label} request failed") from error
