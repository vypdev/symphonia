"""Bounded Spotify playlist-page traversal over an injected request function."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from urllib.parse import quote
from .contracts import ProviderObjectRef, ProviderPlaylistPage
from .errors import ProviderApiError, ProviderErrorCategory
from .http_json import JsonResponse
from .spotify_playlist_mapping import next_offset, parse_cursor, playlist_entry


ReadRequest = Callable[[str, str, str, dict[str, str]], JsonResponse]


def iter_playlist_pages(
    request: ReadRequest,
    connection_id: str,
    playlist: ProviderObjectRef,
    *,
    cursor: str | None,
    page_size: int,
    max_pages: int,
) -> Iterator[ProviderPlaylistPage]:
    if playlist.provider != "spotify" or playlist.object_type != "playlist":
        raise ValueError("Spotify adapter requires a Spotify playlist reference")
    offset = parse_cursor(cursor)
    pages: list[ProviderPlaylistPage] = []
    seen_offsets: set[int] = set()
    while True:
        if len(pages) >= max_pages:
            raise ProviderApiError(
                ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                "Spotify playlist pagination exceeded the configured page limit",
            )
        if offset in seen_offsets:
            raise ProviderApiError(
                ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                "Spotify pagination repeated an offset",
            )
        seen_offsets.add(offset)
        response = request(
            connection_id,
            "GET",
            f"/playlists/{quote(playlist.object_id, safe='')}/items",
            {"limit": str(page_size), "offset": str(offset)},
        )
        items = response.payload.get("items")
        if not isinstance(items, list):
            raise ProviderApiError(
                ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                "Spotify playlist items were not a list",
            )
        entries = tuple(
            playlist_entry(playlist, item, position=offset + index)
            for index, item in enumerate(items)
        )
        next_url = response.payload.get("next")
        if next_url and not entries:
            raise ProviderApiError(
                ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                "Spotify pagination advanced without returning items",
            )
        parsed_offset = next_offset(next_url, offset + len(entries))
        next_cursor = str(parsed_offset) if parsed_offset is not None else None
        pages.append(
            ProviderPlaylistPage(
                playlist=playlist,
                entries=entries,
                cursor=None if not pages and cursor is None else str(offset),
                next_cursor=next_cursor,
                complete=next_cursor is None,
                revision=response.payload.get("snapshot_id")
                if isinstance(response.payload.get("snapshot_id"), str)
                else None,
            )
        )
        yield pages[-1]
        if next_cursor is None:
            return
        if parsed_offset is None:
            raise AssertionError("Spotify pagination cursor was unexpectedly empty")
        offset = parsed_offset


def read_playlist_pages(
    request: ReadRequest, connection_id: str, playlist: ProviderObjectRef, *,
    cursor: str | None, page_size: int, max_pages: int,
) -> tuple[ProviderPlaylistPage, ...]:
    return tuple(iter_playlist_pages(
        request, connection_id, playlist, cursor=cursor, page_size=page_size, max_pages=max_pages,
    ))
