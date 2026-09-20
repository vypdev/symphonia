"""Normalized provider contracts and import collection helpers."""

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
from .connections import ConnectionState, ProviderConnection
from .importing import CollectionImportResult, ImportIssue, collect_playlist_pages, to_playlist_snapshot
from .writing import PlaylistWriter, ProviderWriteError, TargetPlaylist, WriteOutcome, WriteResult

__all__ = [
    "AccessBasis",
    "Capability",
    "CollectionImportResult",
    "ConnectionState",
    "ImportIssue",
    "MediaKind",
    "ProviderAdapter",
    "ProviderCapabilities",
    "ProviderConnection",
    "ProviderManifest",
    "ProviderObjectRef",
    "ProviderPlaylistEntry",
    "ProviderPlaylistPage",
    "ProviderWriteError",
    "PlaylistWriter",
    "TargetPlaylist",
    "WriteOutcome",
    "WriteResult",
    "collect_playlist_pages",
    "to_playlist_snapshot",
]
