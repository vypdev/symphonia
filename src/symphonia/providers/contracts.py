"""Provider-independent ports and normalized provider values.

Provider adapters translate SDK/API payloads into these values. The domain and
application layers never need to import provider SDK classes or infer identity
from URL shapes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Iterable, Protocol


def _require_text(value: object, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


class AccessBasis(str, Enum):
    OFFICIAL = "official"
    UNOFFICIAL = "unofficial"
    BEST_EFFORT = "best_effort"


class Capability(str, Enum):
    READ_PLAYLISTS = "read_playlists"
    READ_LIBRARY = "read_library"
    SEARCH_TRACKS = "search_tracks"
    CREATE_PLAYLIST = "create_playlist"
    ADD_PLAYLIST_ENTRIES = "add_playlist_entries"
    REORDER_PLAYLIST = "reorder_playlist"
    DELETE_PLAYLIST = "delete_playlist"


class MediaKind(str, Enum):
    TRACK = "track"
    VIDEO = "video"
    PODCAST = "podcast"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProviderObjectRef:
    """Opaque external identity with the required type/namespace boundary."""

    provider: str
    object_type: str
    object_id: str
    namespace: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.provider, "provider"),
            (self.object_type, "object_type"),
            (self.object_id, "object_id"),
            (self.namespace, "namespace"),
        ):
            _require_text(value, field_name=field_name)

    @property
    def external_key(self) -> tuple[str, str, str, str]:
        return (self.provider, self.namespace, self.object_type, self.object_id)


@dataclass(frozen=True, slots=True)
class ProviderManifest:
    provider: str
    display_name: str
    access_basis: AccessBasis
    maturity: str
    support_level: str
    upstream_dependencies: tuple[str, ...] = ()
    reviewed_on: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.access_basis, AccessBasis):
            raise ValueError("access_basis must be an AccessBasis value")
        _require_text(self.provider, field_name="provider")
        _require_text(self.display_name, field_name="display_name")
        _require_text(self.maturity, field_name="maturity")
        _require_text(self.support_level, field_name="support_level")
        if any(not isinstance(item, str) or not item.strip() for item in self.upstream_dependencies):
            raise ValueError("upstream_dependencies must contain non-empty strings")
        if self.reviewed_on is not None:
            _require_text(self.reviewed_on, field_name="reviewed_on")
            try:
                date.fromisoformat(self.reviewed_on)
            except ValueError as error:
                raise ValueError("reviewed_on must be an ISO date") from error


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Effective capabilities after adapter/connection/object/health checks."""

    enabled: frozenset[Capability]
    evidence_version: str
    observed_at: str

    def __post_init__(self) -> None:
        if any(not isinstance(item, Capability) for item in self.enabled):
            raise ValueError("enabled must contain Capability values")
        _require_text(self.evidence_version, field_name="evidence_version")
        _require_text(self.observed_at, field_name="observed_at")

    def supports(self, capability: Capability) -> bool:
        return capability in self.enabled


@dataclass(frozen=True, slots=True)
class ProviderPlaylistEntry:
    occurrence_id: str
    position: int
    track: ProviderObjectRef
    media_kind: MediaKind
    title: str | None = None
    available: bool = True
    source_added_at: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.occurrence_id, field_name="occurrence_id")
        if isinstance(self.position, bool) or not isinstance(self.position, int):
            raise ValueError("position must be an integer")
        if self.position < 0:
            raise ValueError("position must be non-negative")
        if not isinstance(self.track, ProviderObjectRef):
            raise ValueError("track must be a ProviderObjectRef")
        if not isinstance(self.media_kind, MediaKind):
            raise ValueError("media_kind must be a MediaKind value")
        if self.title is not None and not isinstance(self.title, str):
            raise ValueError("title must be a string when provided")
        if self.source_added_at is not None and not isinstance(self.source_added_at, str):
            raise ValueError("source_added_at must be a string when provided")
        if not isinstance(self.available, bool):
            raise ValueError("available must be a boolean")


@dataclass(frozen=True, slots=True)
class ProviderPlaylistPage:
    playlist: ProviderObjectRef
    entries: tuple[ProviderPlaylistEntry, ...]
    cursor: str | None
    next_cursor: str | None
    complete: bool
    revision: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.playlist, ProviderObjectRef):
            raise ValueError("playlist must be a ProviderObjectRef")
        if self.playlist.object_type not in {"playlist", "library-playlists"}:
            raise ValueError("playlist page requires a playlist or library-playlists object reference")
        if not isinstance(self.entries, tuple):
            raise ValueError("entries must be a tuple")
        if not isinstance(self.complete, bool):
            raise ValueError("complete must be a boolean")
        if any(not isinstance(entry, ProviderPlaylistEntry) for entry in self.entries):
            raise ValueError("entries must contain ProviderPlaylistEntry values")
        positions = [entry.position for entry in self.entries]
        if positions != sorted(positions):
            raise ValueError("page entries must be ordered by position")
        if len(positions) != len(set(positions)):
            raise ValueError("page entry positions must be unique")
        if self.complete and self.next_cursor is not None:
            raise ValueError("a complete page cannot have a next_cursor")
        for value, field_name in (
            (self.cursor, "cursor"),
            (self.next_cursor, "next_cursor"),
            (self.revision, "revision"),
        ):
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{field_name} must be a string when provided")


class ProviderAdapter(Protocol):
    """Semantic adapter port used by application use cases."""

    @property
    def manifest(self) -> ProviderManifest: ...

    def capabilities(self, connection_id: str) -> ProviderCapabilities: ...

    def read_playlist_pages(
        self, connection_id: str, playlist: ProviderObjectRef, cursor: str | None = None
    ) -> Iterable[ProviderPlaylistPage]: ...
