"""Validate the durable playlist-import intent before an adapter read."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from symphonia.providers.contracts import ProviderObjectRef


def parse_import_payload(
    payload: Mapping[str, Any],
) -> tuple[str, ProviderObjectRef, str, datetime]:
    connection_id = payload.get("connection_id")
    snapshot_id = payload.get("snapshot_id")
    observed_at = payload.get("observed_at")
    raw_playlist = payload.get("playlist")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (connection_id, snapshot_id, observed_at)
    ):
        raise ValueError("import operation payload is missing required fields")
    if not isinstance(raw_playlist, Mapping):
        raise ValueError("import operation payload has no playlist reference")
    try:
        playlist = ProviderObjectRef(
            raw_playlist["provider"],
            raw_playlist["object_type"],
            raw_playlist["object_id"],
            raw_playlist["namespace"],
        )
        parsed_observed_at = datetime.fromisoformat(observed_at)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("import operation payload has an invalid playlist or timestamp") from error
    if payload.get("provider") != playlist.provider:
        raise ValueError("import operation provider does not match playlist")
    if parsed_observed_at.tzinfo is None:
        raise ValueError("import operation observed_at must be timezone-aware")
    return connection_id, playlist, snapshot_id, parsed_observed_at.astimezone(timezone.utc)
