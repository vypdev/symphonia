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
from .youtube import YouTubeDataAdapter
from .apple_music import AppleJsonResponse, AppleMusicAdapter, UrllibAppleMusicClient
from .capabilities import CapabilityError, CapabilityLayers, missing_capabilities, require_capabilities
from .importing import CollectionImportResult, ImportIssue, collect_playlist_pages, to_playlist_snapshot
from .writing import PlaylistWriter, ProviderWriteError, TargetPlaylist, WriteOutcome, WriteResult

__all__ = [
    "AccessBasis",
    "AuthorizationAttempt",
    "AuthorizationState",
    "Capability",
    "CapabilityError",
    "CapabilityLayers",
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
    "YouTubeDataAdapter",
    "AppleMusicAdapter",
    "AppleJsonResponse",
    "UrllibAppleMusicClient",
    "ProviderWriteError",
    "PlaylistWriter",
    "TargetPlaylist",
    "WriteOutcome",
    "WriteResult",
    "collect_playlist_pages",
    "missing_capabilities",
    "require_capabilities",
    "to_playlist_snapshot",
]
