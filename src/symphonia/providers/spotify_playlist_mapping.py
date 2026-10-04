"""Validate Spotify playlist offsets and normalize individual playlist items."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .contracts import MediaKind, ProviderObjectRef, ProviderPlaylistEntry
from .errors import ProviderApiError, ProviderErrorCategory


def parse_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not isinstance(cursor, str) or not cursor.strip():
        raise ValueError("Spotify playlist cursor must be a non-empty string offset")
    try:
        value = int(cursor)
    except ValueError as error:
        raise ValueError("Spotify playlist cursor must be an integer offset") from error
    if value < 0:
        raise ValueError("Spotify playlist cursor must not be negative")
    return value


def next_offset(next_url: Any, fallback: int) -> int | None:
    if not next_url:
        return None
    if not isinstance(next_url, str):
        raise ProviderApiError(
            ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
            "Spotify pagination next link was not a URL",
        )
    try:
        parsed = urlsplit(next_url)
    except ValueError as error:
        raise ProviderApiError(
            ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
            "Spotify pagination next link was malformed",
        ) from error
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProviderApiError(
            ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
            "Spotify pagination next link was not an absolute URL",
        )
    values = parse_qs(parsed.query, keep_blank_values=True).get("offset")
    if values is None or len(values) != 1:
        raise ProviderApiError(
            ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
            "Spotify pagination next link did not contain one offset",
        )
    try:
        offset = parse_cursor(values[0])
    except ValueError as error:
        raise ProviderApiError(
            ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
            "Spotify pagination next link contained an invalid offset",
        ) from error
    if offset < fallback:
        raise ProviderApiError(
            ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
            "Spotify pagination moved backwards",
        )
    return offset


def playlist_entry(
    playlist: ProviderObjectRef, item: Any, *, position: int,
) -> ProviderPlaylistEntry:
    item_payload = (item.get("item") or item.get("track")) if isinstance(item, Mapping) else None
    if not isinstance(item_payload, Mapping):
        ref = ProviderObjectRef("spotify", "track", f"unavailable:{position}", playlist.namespace)
        return ProviderPlaylistEntry(
            f"{playlist.object_id}:{position}", position, ref, MediaKind.UNKNOWN,
            available=False,
        )
    object_type = str(item_payload.get("type") or "unknown")
    object_id = str(item_payload.get("id") or f"unavailable:{position}")
    media_kind = {"track": MediaKind.TRACK, "episode": MediaKind.PODCAST}.get(
        object_type, MediaKind.UNKNOWN,
    )
    available = (
        bool(item_payload.get("id"))
        and media_kind is not MediaKind.UNKNOWN
        and item_payload.get("is_playable", True) is not False
    )
    ref = ProviderObjectRef("spotify", object_type, object_id, playlist.namespace)
    return ProviderPlaylistEntry(
        occurrence_id=f"{playlist.object_id}:{position}",
        position=position,
        track=ref,
        media_kind=media_kind,
        title=item_payload.get("name") if isinstance(item_payload.get("name"), str) else None,
        available=available,
        source_added_at=item.get("added_at")
        if isinstance(item, Mapping) and isinstance(item.get("added_at"), str) else None,
    )
