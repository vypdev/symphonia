"""Offline-testable Spotify Web API adapter for playlist reads.

The adapter owns only normalized translation and error classification. Token
refresh/storage and the concrete HTTP transport are injected at composition
time, so no secret material enters this module's persistence or logs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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
from .writing import PlaylistWriter, ProviderWriteError, TargetPlaylist, WriteOutcome, WriteResult


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
    """Small standard-library transport with bounded request timeout."""

    def __init__(self, base_url: str = "https://api.spotify.com/v1", timeout_seconds: float = 10.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

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
            raise ProviderApiError(ProviderErrorCategory.TIMEOUT, "Spotify request timed out") from error
        except URLError as error:
            raise ProviderApiError(ProviderErrorCategory.NETWORK_ERROR, "Spotify request failed") from error


class SpotifyAdapter(ProviderAdapter, PlaylistWriter):
    """Translate Spotify playlist pages into Symphonia provider values."""

    manifest = ProviderManifest(
        provider="spotify",
        display_name="Spotify",
        access_basis=AccessBasis.OFFICIAL,
        maturity="beta",
        support_level="playlist-read/write",
        upstream_dependencies=("Spotify Web API",),
        reviewed_on="2026-09-20",
    )

    def __init__(
        self,
        client: JsonClient,
        token_for_connection: Callable[[str], str],
        page_size: int = 50,
        connection_id: str | None = None,
        allow_writes: bool = False,
    ) -> None:
        if not 1 <= page_size <= 50:
            raise ValueError("Spotify playlist page_size must be between 1 and 50")
        self._client = client
        self._token_for_connection = token_for_connection
        self._page_size = page_size
        self._connection_id = connection_id
        self._allow_writes = allow_writes

    def capabilities(self, connection_id: str) -> ProviderCapabilities:
        response = self._request(connection_id, "GET", "/me/playlists", {"limit": "1", "offset": "0"})
        enabled = {Capability.READ_PLAYLISTS}
        if self._allow_writes and self._connection_id == connection_id:
            enabled.update({Capability.CREATE_PLAYLIST, Capability.ADD_PLAYLIST_ENTRIES})
        return ProviderCapabilities(
            enabled=frozenset(enabled),
            evidence_version="spotify-playlist-read-write-v1" if len(enabled) > 1 else "spotify-playlist-read-v1",
            observed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    def read_playlist_pages(
        self,
        connection_id: str,
        playlist: ProviderObjectRef,
        cursor: str | None = None,
    ) -> tuple[ProviderPlaylistPage, ...]:
        if playlist.provider != self.manifest.provider or playlist.object_type != "playlist":
            raise ValueError("Spotify adapter requires a Spotify playlist reference")
        offset = self._parse_cursor(cursor)
        pages: list[ProviderPlaylistPage] = []
        while True:
            response = self._request(
                connection_id,
                "GET",
                f"/playlists/{playlist.object_id}/items",
                {"limit": str(self._page_size), "offset": str(offset)},
            )
            items = response.payload.get("items", [])
            if not isinstance(items, list):
                raise ProviderApiError(ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED, "Spotify playlist items were not a list")
            entries = tuple(
                self._entry(playlist, item, position=offset + index)
                for index, item in enumerate(items)
            )
            next_url = response.payload.get("next")
            if next_url and not entries:
                raise ProviderApiError(
                    ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                    "Spotify pagination advanced without returning items",
                )
            next_cursor = str(offset + len(entries)) if next_url else None
            pages.append(
                ProviderPlaylistPage(
                    playlist=playlist,
                    entries=entries,
                    cursor=None if not pages and cursor is None else str(offset),
                    next_cursor=next_cursor,
                    complete=next_cursor is None,
                    revision=response.payload.get("snapshot_id"),
                )
            )
            if next_cursor is None:
                return tuple(pages)
            offset += len(entries)

    def ensure_target_playlist(
        self,
        *,
        provider: str,
        name: str,
        visibility: str,
        idempotency_key: str,
    ) -> TargetPlaylist:
        if provider != self.manifest.provider:
            raise ValueError("Spotify adapter requires a Spotify target provider")
        connection_id = self._write_connection_id()
        try:
            response = self._request(
                connection_id,
                "POST",
                "/me/playlists",
                {},
                body={"name": name, "public": visibility == "public"},
            )
            playlist_id = response.payload.get("id")
            if not isinstance(playlist_id, str) or not playlist_id.strip():
                raise ProviderApiError(
                    ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                    "Spotify create-playlist response did not contain an id",
                )
            return TargetPlaylist(playlist_id)
        except ProviderApiError as error:
            raise ProviderWriteError(
                self._write_outcome(error),
                error.detail,
                error.provider_code,
                error.retry_at,
            ) from error

    def add_entry(
        self,
        *,
        target_playlist_id: str,
        provider_track_id: str,
        idempotency_key: str,
    ) -> WriteResult:
        try:
            connection_id = self._write_connection_id()
        except ProviderWriteError as error:
            return WriteResult(error.outcome, provider_code=error.provider_code, detail=error.detail)
        try:
            self._request(
                connection_id,
                "POST",
                f"/playlists/{target_playlist_id}/items",
                {},
                body={"uris": [f"spotify:track:{provider_track_id}"]},
            )
            return WriteResult(WriteOutcome.CONFIRMED_SUCCESS)
        except ProviderApiError as error:
            return WriteResult(
                self._write_outcome(error),
                provider_code=error.provider_code,
                detail=error.detail,
                retry_at=error.retry_at,
            )

    def reconcile_target_playlist(self, *, idempotency_key: str) -> TargetPlaylist | None:
        # Spotify does not expose the local idempotency key, so a timed-out
        # create cannot be identified safely without a provider-specific
        # correlation strategy. The executor therefore pauses for review.
        return None

    def reconcile_entry(self, *, target_playlist_id: str, provider_track_id: str, idempotency_key: str) -> bool:
        # Existing duplicate occurrences make a positive read insufficient to
        # prove which add attempt was accepted. Never claim certainty here.
        return False

    def _write_connection_id(self) -> str:
        if self._connection_id is None or not self._connection_id.strip():
            raise ProviderWriteError(
                WriteOutcome.PERMANENT_FAILURE,
                "Spotify writer is not bound to a provider connection",
            )
        return self._connection_id

    def _request(
        self,
        connection_id: str,
        method: str,
        path: str,
        query: Mapping[str, str],
        body: Mapping[str, Any] | None = None,
    ) -> JsonResponse:
        token = self._token_for_connection(connection_id)
        if not token.strip():
            raise ProviderApiError(ProviderErrorCategory.AUTHENTICATION_REQUIRED, "Spotify connection has no usable access token")
        response = self._client.request(method, path, token=token, query=query, body=body)
        if 200 <= response.status < 300:
            if not isinstance(response.payload, Mapping):
                raise ProviderApiError(
                    ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                    "Spotify response was not a JSON object",
                )
            return response
        category = {
            401: ProviderErrorCategory.AUTHENTICATION_REQUIRED,
            403: ProviderErrorCategory.PERMISSION_DENIED,
            404: ProviderErrorCategory.NOT_FOUND,
            429: ProviderErrorCategory.RATE_LIMITED,
        }.get(response.status, ProviderErrorCategory.PROVIDER_UNAVAILABLE if response.status >= 500 else ProviderErrorCategory.INVALID_REQUEST)
        retry_at = None
        retry_after = self._header(response.headers, "retry-after")
        if category is ProviderErrorCategory.RATE_LIMITED and retry_after is not None:
            try:
                retry_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, int(retry_after)))
            except ValueError:
                retry_at = None
        error_body = response.payload.get("error") if isinstance(response.payload, Mapping) else None
        provider_code = str(error_body.get("status")) if isinstance(error_body, Mapping) and error_body.get("status") is not None else str(response.status)
        raise ProviderApiError(category, "Spotify API request was not accepted", provider_code=provider_code, retry_at=retry_at)

    @staticmethod
    def _write_outcome(error: ProviderApiError) -> WriteOutcome:
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

    @staticmethod
    def _parse_cursor(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            value = int(cursor)
        except ValueError as error:
            raise ValueError("Spotify playlist cursor must be an integer offset") from error
        if value < 0:
            raise ValueError("Spotify playlist cursor must not be negative")
        return value

    @staticmethod
    def _entry(playlist: ProviderObjectRef, item: Any, *, position: int) -> ProviderPlaylistEntry:
        item_payload = (item.get("item") or item.get("track")) if isinstance(item, Mapping) else None
        if not isinstance(item_payload, Mapping):
            ref = ProviderObjectRef("spotify", "track", f"unavailable:{position}", playlist.namespace)
            return ProviderPlaylistEntry(f"{playlist.object_id}:{position}", position, ref, MediaKind.UNKNOWN, available=False)
        object_type = str(item_payload.get("type") or "unknown")
        object_id = str(item_payload.get("id") or f"unavailable:{position}")
        media_kind = {"track": MediaKind.TRACK, "episode": MediaKind.PODCAST}.get(object_type, MediaKind.UNKNOWN)
        available = bool(item_payload.get("id")) and media_kind is not MediaKind.UNKNOWN and item_payload.get("is_playable", True) is not False
        ref = ProviderObjectRef("spotify", object_type, object_id, playlist.namespace)
        return ProviderPlaylistEntry(
            occurrence_id=f"{playlist.object_id}:{position}",
            position=position,
            track=ref,
            media_kind=media_kind,
            title=item_payload.get("name") if isinstance(item_payload.get("name"), str) else None,
            available=available,
            source_added_at=item.get("added_at") if isinstance(item, Mapping) and isinstance(item.get("added_at"), str) else None,
        )

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str | None:
        wanted = name.lower()
        return next((value for key, value in headers.items() if key.lower() == wanted), None)
