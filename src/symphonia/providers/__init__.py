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
from .authorization import AuthorizationAttempt, AuthorizationState
from .registry import ProviderAlreadyRegistered, ProviderNotRegistered, ProviderRegistry
from .errors import ProviderApiError, ProviderErrorCategory
from .spotify import JsonResponse, SpotifyAdapter, UrllibJsonClient
from .importing import CollectionImportResult, ImportIssue, collect_playlist_pages, to_playlist_snapshot
from .writing import PlaylistWriter, ProviderWriteError, TargetPlaylist, WriteOutcome, WriteResult

__all__ = [
    "AccessBasis",
    "AuthorizationAttempt",
    "AuthorizationState",
    "Capability",
    "CollectionImportResult",
    "ConnectionState",
    "ImportIssue",
    "MediaKind",
    "ProviderAdapter",
    "ProviderApiError",
    "ProviderAlreadyRegistered",
    "ProviderErrorCategory",
    "ProviderCapabilities",
    "ProviderConnection",
    "ProviderManifest",
    "ProviderObjectRef",
    "ProviderNotRegistered",
    "ProviderPlaylistEntry",
    "ProviderPlaylistPage",
    "ProviderRegistry",
    "JsonResponse",
    "SpotifyAdapter",
    "UrllibJsonClient",
    "ProviderWriteError",
    "PlaylistWriter",
    "TargetPlaylist",
    "WriteOutcome",
    "WriteResult",
    "collect_playlist_pages",
    "to_playlist_snapshot",
]
