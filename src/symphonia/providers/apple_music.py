"""Offline-testable Apple Music library-playlist reader."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, parse_qs, urlsplit
from urllib.request import Request, urlopen

from .contracts import (
    AccessBasis,
    Capability,
    MediaKind,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderManifest,
    ProviderObjectRef,
    ProviderPlaylistEntry,
    ProviderPlaylistPage,
)
from .errors import ProviderApiError, ProviderErrorCategory


class AppleJsonClient(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        developer_token: str,
        user_token: str,
        query: Mapping[str, str],
    ) -> "AppleJsonResponse": ...


class AppleJsonResponse:
    def __init__(self, status: int, payload: Mapping[str, Any], headers: Mapping[str, str]) -> None:
        self.status = status
        self.payload = payload
        self.headers = headers


class UrllibAppleMusicClient:
    def __init__(self, base_url: str = "https://api.music.apple.com/v1", timeout_seconds: float = 10.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        path: str,
        *,
        developer_token: str,
        user_token: str,
        query: Mapping[str, str],
    ) -> AppleJsonResponse:
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query)}"
        request = Request(
            url,
            method=method,
            headers={
                "Authorization": f"Bearer {developer_token}",
                "Music-User-Token": user_token,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read()
                payload = json.loads(body.decode("utf-8")) if body else {}
                return AppleJsonResponse(response.status, payload, dict(response.headers.items()))
        except HTTPError as error:
            body = error.read()
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = {}
            return AppleJsonResponse(error.code, payload, dict(error.headers.items()))
        except TimeoutError as error:
            raise ProviderApiError(ProviderErrorCategory.TIMEOUT, "Apple Music request timed out") from error
        except URLError as error:
            raise ProviderApiError(ProviderErrorCategory.NETWORK_ERROR, "Apple Music request failed") from error


class AppleMusicAdapter(ProviderAdapter):
    manifest = ProviderManifest(
        provider="apple_music",
        display_name="Apple Music",
        access_basis=AccessBasis.OFFICIAL,
        maturity="experimental",
        support_level="library-playlist-read",
        upstream_dependencies=("Apple Music API", "MusicKit user authentication"),
        reviewed_on="2026-09-20",
    )

    def __init__(
        self,
        client: AppleJsonClient | None,
        tokens_for_connection: Callable[[str], tuple[str, str]],
        page_size: int = 25,
    ) -> None:
        if not 1 <= page_size <= 100:
            raise ValueError("Apple Music playlist page_size must be between 1 and 100")
        self._client = client or UrllibAppleMusicClient()
        self._tokens_for_connection = tokens_for_connection
        self._page_size = page_size

    def capabilities(self, connection_id: str) -> ProviderCapabilities:
        self._request(connection_id, "/me/library/playlists", {"limit": "1", "offset": "0"})
        return ProviderCapabilities(
            enabled=frozenset({Capability.READ_PLAYLISTS}),
            evidence_version="apple-library-playlist-read-v1",
            observed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    def read_playlist_pages(
        self,
        connection_id: str,
        playlist: ProviderObjectRef,
        cursor: str | None = None,
    ) -> tuple[ProviderPlaylistPage, ...]:
        if playlist.provider != self.manifest.provider or playlist.object_type != "library-playlists":
            raise ValueError("Apple Music adapter requires an apple_music library-playlists reference")
        offset = self._parse_offset(cursor)
        pages: list[ProviderPlaylistPage] = []
        seen_offsets: set[int] = set()
        while True:
            if offset in seen_offsets:
                raise ProviderApiError(
                    ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                    "Apple Music pagination repeated an offset",
                )
            seen_offsets.add(offset)
            response = self._request(
                connection_id,
                f"/me/library/playlists/{playlist.object_id}/tracks",
                {"limit": str(self._page_size), "offset": str(offset)},
            )
            items = response.payload.get("data", [])
            if not isinstance(items, list):
                raise ProviderApiError(ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED, "Apple Music playlist data was not a list")
            entries = tuple(self._entry(playlist, item, offset + index) for index, item in enumerate(items))
            next_url = response.payload.get("next")
            if next_url and not entries:
                raise ProviderApiError(
                    ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                    "Apple Music pagination advanced without returning items",
                )
            next_offset = self._next_offset(next_url, offset + len(entries))
            pages.append(
                ProviderPlaylistPage(
                    playlist=playlist,
                    entries=entries,
                    cursor=None if not pages and cursor is None else str(offset),
                    next_cursor=None if next_offset is None else str(next_offset),
                    complete=next_offset is None,
                    revision=response.payload.get("etag"),
                )
            )
            if next_offset is None:
                return tuple(pages)
            offset = next_offset

    def _request(self, connection_id: str, path: str, query: Mapping[str, str]) -> AppleJsonResponse:
        developer_token, user_token = self._tokens_for_connection(connection_id)
        if not developer_token.strip() or not user_token.strip():
            raise ProviderApiError(ProviderErrorCategory.AUTHENTICATION_REQUIRED, "Apple Music connection has no usable tokens")
        response = self._client.request(
            "GET",
            path,
            developer_token=developer_token,
            user_token=user_token,
            query=query,
        )
        if 200 <= response.status < 300:
            if not isinstance(response.payload, Mapping):
                raise ProviderApiError(ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED, "Apple Music response was not a JSON object")
            return response
        category = {
            401: ProviderErrorCategory.AUTHENTICATION_REQUIRED,
            403: ProviderErrorCategory.PERMISSION_DENIED,
            404: ProviderErrorCategory.NOT_FOUND,
            429: ProviderErrorCategory.RATE_LIMITED,
        }.get(response.status, ProviderErrorCategory.PROVIDER_UNAVAILABLE if response.status >= 500 else ProviderErrorCategory.INVALID_REQUEST)
        retry_at = None
        retry_after = next((value for key, value in response.headers.items() if key.lower() == "retry-after"), None)
        if category is ProviderErrorCategory.RATE_LIMITED and retry_after is not None:
            try:
                retry_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, int(retry_after)))
            except ValueError:
                retry_at = None
        provider_code = str(response.status)
        if isinstance(response.payload.get("errors"), list) and response.payload["errors"]:
            first = response.payload["errors"][0]
            if isinstance(first, Mapping) and first.get("code"):
                provider_code = str(first["code"])
        raise ProviderApiError(category, "Apple Music API request was not accepted", provider_code=provider_code, retry_at=retry_at)

    @staticmethod
    def _parse_offset(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            value = int(cursor)
        except ValueError as error:
            raise ValueError("Apple Music playlist cursor must be an integer offset") from error
        if value < 0:
            raise ValueError("Apple Music playlist cursor must not be negative")
        return value

    @staticmethod
    def _next_offset(next_url: Any, fallback: int) -> int | None:
        if not next_url:
            return None
        if isinstance(next_url, str):
            values = parse_qs(urlsplit(next_url).query).get("offset")
            if values:
                return AppleMusicAdapter._parse_offset(values[0])
        return fallback

    @staticmethod
    def _entry(playlist: ProviderObjectRef, item: Any, position: int) -> ProviderPlaylistEntry:
        if not isinstance(item, Mapping):
            item = {}
        object_id = item.get("id")
        available = isinstance(object_id, str) and bool(object_id.strip())
        object_id = object_id if available else f"unavailable:{position}"
        object_type = str(item.get("type") or "songs")
        attributes = item.get("attributes") if isinstance(item.get("attributes"), Mapping) else {}
        return ProviderPlaylistEntry(
            occurrence_id=f"{playlist.object_id}:{position}",
            position=position,
            track=ProviderObjectRef("apple_music", object_type, object_id, playlist.namespace),
            media_kind=MediaKind.TRACK,
            title=attributes.get("name") if isinstance(attributes.get("name"), str) else None,
            available=available,
        )
