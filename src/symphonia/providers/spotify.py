"""Offline-testable Spotify Web API adapter for playlist reads.

The adapter owns only normalized translation and error classification. Token
refresh/storage and the concrete HTTP transport are injected at composition
time, so no secret material enters this module's persistence or logs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from .contracts import (
    AccessBasis,
    Capability,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderManifest,
    ProviderObjectRef,
    ProviderPlaylistPage,
)
from .errors import ProviderApiError, ProviderErrorCategory
from .http_json import JsonClient, JsonResponse, UrllibJsonClient
from .spotify_error_mapping import classify_response, write_outcome
from .spotify_playlist_reader import read_playlist_pages
from .writing import PlaylistWriter, ProviderWriteError, TargetPlaylist, WriteOutcome, WriteResult


class SpotifyAdapter(ProviderAdapter, PlaylistWriter):
    """Translate Spotify playlist pages into Symphonia provider values."""

    manifest = ProviderManifest(
        provider="spotify",
        display_name="Spotify",
        access_basis=AccessBasis.OFFICIAL,
        maturity="beta",
        support_level="playlist-read/write",
        upstream_dependencies=("Spotify Web API",),
        reviewed_on="2026-09-22",
    )

    def __init__(
        self,
        client: JsonClient,
        token_for_connection: Callable[[str], str],
        page_size: int = 50,
        connection_id: str | None = None,
        allow_writes: bool = False,
        max_pages: int = 10_000,
    ) -> None:
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 50:
            raise ValueError("Spotify playlist page_size must be between 1 and 50")
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages <= 0:
            raise ValueError("Spotify max_pages must be positive")
        self._client = client
        self._token_for_connection = token_for_connection
        self._page_size = page_size
        self._connection_id = connection_id
        self._allow_writes = allow_writes
        self._max_pages = max_pages

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
        return read_playlist_pages(
            self._request, connection_id, playlist, cursor=cursor,
            page_size=self._page_size, max_pages=self._max_pages,
        )

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
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Spotify playlist name must not be empty")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("Spotify playlist idempotency_key must not be empty")
        if visibility not in {"private", "public"}:
            raise ValueError("Spotify playlist visibility must be private or public")
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
                write_outcome(error),
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
        if (
            not isinstance(target_playlist_id, str)
            or not target_playlist_id.strip()
            or not isinstance(provider_track_id, str)
            or not provider_track_id.strip()
            or not isinstance(idempotency_key, str)
            or not idempotency_key.strip()
        ):
            raise ValueError("Spotify write identifiers must not be empty")
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
                write_outcome(error),
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
        if not isinstance(token, str) or not token.strip():
            raise ProviderApiError(ProviderErrorCategory.AUTHENTICATION_REQUIRED, "Spotify connection has no usable access token")
        response = self._client.request(method, path, token=token, query=query, body=body)
        if 200 <= response.status < 300:
            if not isinstance(response.payload, Mapping):
                raise ProviderApiError(
                    ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                    "Spotify response was not a JSON object",
                )
            return response
        raise classify_response(response)
