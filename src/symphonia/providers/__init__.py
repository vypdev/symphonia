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
from .importing import CollectionImportResult, ImportIssue, collect_playlist_pages, to_playlist_snapshot
from .writing import PlaylistWriter, ProviderWriteError, TargetPlaylist, WriteOutcome, WriteResult

__all__ = [
    "AccessBasis",
    "Capability",
    "CollectionImportResult",
    "ImportIssue",
    "MediaKind",
    "ProviderAdapter",
    "ProviderCapabilities",
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
