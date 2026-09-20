"""Official YouTube Data API adapter for video-playlist reads.

This is intentionally not a YouTube Music adapter. The provider ID and
manifest make the narrower video-playlist contract visible to planning/UI.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

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
from .spotify import JsonClient, UrllibJsonClient


class YouTubeDataAdapter(ProviderAdapter):
    """Translate ``playlistItems.list`` pages into normalized video entries."""

    manifest = ProviderManifest(
        provider="youtube_data",
        display_name="YouTube Data API (video playlists)",
        access_basis=AccessBasis.OFFICIAL,
        maturity="experimental",
        support_level="video-playlist-read",
        upstream_dependencies=("YouTube Data API v3",),
        reviewed_on="2026-09-20",
    )

    def __init__(
        self,
        client: JsonClient | None,
        token_for_connection: Callable[[str], str],
        page_size: int = 50,
        api_key: str | None = None,
        max_pages: int = 10_000,
    ) -> None:
        if not 1 <= page_size <= 50:
            raise ValueError("YouTube playlist page_size must be between 1 and 50")
        if max_pages <= 0:
            raise ValueError("YouTube max_pages must be positive")
        self._client = client or UrllibJsonClient("https://www.googleapis.com/youtube/v3")
        self._token_for_connection = token_for_connection
        self._page_size = page_size
        self._api_key = api_key
        self._max_pages = max_pages

    def capabilities(self, connection_id: str) -> ProviderCapabilities:
        self._request(
            connection_id,
            "/channels",
            {"part": "id", "mine": "true", "maxResults": "1"},
        )
        return ProviderCapabilities(
            enabled=frozenset({Capability.READ_PLAYLISTS}),
            evidence_version="youtube-data-video-playlist-read-v1",
            observed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    def read_playlist_pages(
        self,
        connection_id: str,
        playlist: ProviderObjectRef,
        cursor: str | None = None,
    ) -> tuple[ProviderPlaylistPage, ...]:
        if playlist.provider != self.manifest.provider or playlist.object_type != "playlist":
            raise ValueError("YouTube Data adapter requires a youtube_data playlist reference")
        page_token = cursor
        pages: list[ProviderPlaylistPage] = []
        position = 0
        seen_tokens: set[str | None] = set()
        while True:
            if len(pages) >= self._max_pages:
                raise ProviderApiError(
                    ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                    "YouTube playlist pagination exceeded the configured page limit",
                )
            if page_token in seen_tokens:
                raise ProviderApiError(
                    ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                    "YouTube pagination repeated a page token",
                )
            seen_tokens.add(page_token)
            query = {
                "part": "snippet,contentDetails",
                "playlistId": playlist.object_id,
                "maxResults": str(self._page_size),
            }
            if page_token is not None:
                query["pageToken"] = page_token
            response = self._request(connection_id, "/playlistItems", query)
            items = response.payload.get("items", [])
            if not isinstance(items, list):
                raise ProviderApiError(ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED, "YouTube playlist items were not a list")
            entries = tuple(
                self._entry(playlist, item, position=position + index)
                for index, item in enumerate(items)
            )
            next_token = response.payload.get("nextPageToken")
            if next_token and not entries:
                raise ProviderApiError(
                    ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                    "YouTube pagination advanced without returning items",
                )
            pages.append(
                ProviderPlaylistPage(
                    playlist=playlist,
                    entries=entries,
                    cursor=page_token,
                    next_cursor=str(next_token) if next_token else None,
                    complete=not bool(next_token),
                    revision=response.payload.get("etag"),
                )
            )
            if not next_token:
                return tuple(pages)
            page_token = str(next_token)
            position += len(entries)

    def _request(self, connection_id: str, path: str, query: Mapping[str, str]):
        token = self._token_for_connection(connection_id)
        if not token.strip():
            raise ProviderApiError(ProviderErrorCategory.AUTHENTICATION_REQUIRED, "YouTube connection has no usable access token")
        complete_query = dict(query)
        if self._api_key:
            complete_query["key"] = self._api_key
        response = self._client.request("GET", path, token=token, query=complete_query)
        if 200 <= response.status < 300:
            if not isinstance(response.payload, Mapping):
                raise ProviderApiError(ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED, "YouTube response was not a JSON object")
            return response
        error_payload = response.payload.get("error") if isinstance(response.payload, Mapping) else None
        errors = error_payload.get("errors") if isinstance(error_payload, Mapping) else None
        reason = errors[0].get("reason") if isinstance(errors, list) and errors and isinstance(errors[0], Mapping) else None
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
        raise ProviderApiError(category, "YouTube Data API request was not accepted", provider_code=str(reason or response.status), retry_at=retry_at)

    @staticmethod
    def _entry(playlist: ProviderObjectRef, item: Any, *, position: int) -> ProviderPlaylistEntry:
        snippet = item.get("snippet") if isinstance(item, Mapping) else None
        content = item.get("contentDetails") if isinstance(item, Mapping) else None
        snippet = snippet if isinstance(snippet, Mapping) else {}
        content = content if isinstance(content, Mapping) else {}
        resource = snippet.get("resourceId")
        resource = resource if isinstance(resource, Mapping) else {}
        video_id = resource.get("videoId") or content.get("videoId")
        available = isinstance(video_id, str) and bool(video_id.strip())
        object_id = video_id if available else f"unavailable:{position}"
        occurrence_id = str(item.get("id")) if isinstance(item, Mapping) and item.get("id") else f"{playlist.object_id}:{position}"
        return ProviderPlaylistEntry(
            occurrence_id=occurrence_id,
            position=position,
            track=ProviderObjectRef("youtube_data", "video", object_id, playlist.namespace),
            media_kind=MediaKind.VIDEO,
            title=snippet.get("title") if isinstance(snippet.get("title"), str) else None,
            available=available,
            source_added_at=snippet.get("publishedAt") if isinstance(snippet.get("publishedAt"), str) else None,
        )
