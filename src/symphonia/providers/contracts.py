"""Provider-independent ports and normalized provider values.

Provider adapters translate SDK/API payloads into these values. The domain and
application layers never need to import provider SDK classes or infer identity
from URL shapes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Protocol


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
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")

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
        if not self.provider.strip() or not self.display_name.strip():
            raise ValueError("provider and display_name must not be empty")
        if not self.maturity.strip() or not self.support_level.strip():
            raise ValueError("maturity and support_level must not be empty")


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Effective capabilities after adapter/connection/object/health checks."""

    enabled: frozenset[Capability]
    evidence_version: str
    observed_at: str

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
        if not self.occurrence_id.strip():
            raise ValueError("occurrence_id must not be empty")
        if self.position < 0:
            raise ValueError("position must be non-negative")


@dataclass(frozen=True, slots=True)
class ProviderPlaylistPage:
    playlist: ProviderObjectRef
    entries: tuple[ProviderPlaylistEntry, ...]
    cursor: str | None
    next_cursor: str | None
    complete: bool
    revision: str | None = None

    def __post_init__(self) -> None:
        if self.playlist.object_type not in {"playlist", "library-playlists"}:
            raise ValueError("playlist page requires a playlist or library-playlists object reference")
        positions = [entry.position for entry in self.entries]
        if positions != sorted(positions):
            raise ValueError("page entries must be ordered by position")
        if self.complete and self.next_cursor is not None:
            raise ValueError("a complete page cannot have a next_cursor")


class ProviderAdapter(Protocol):
    """Semantic adapter port used by application use cases."""

    @property
    def manifest(self) -> ProviderManifest: ...

    def capabilities(self, connection_id: str) -> ProviderCapabilities: ...

    def read_playlist_pages(
        self, connection_id: str, playlist: ProviderObjectRef, cursor: str | None = None
    ) -> Iterable[ProviderPlaylistPage]: ...
