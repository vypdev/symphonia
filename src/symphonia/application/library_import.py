"""Application use case for publishing normalized playlist imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from symphonia.infrastructure.sqlite_library import PlaylistProjectionRepository, StoredPlaylistSnapshot
from symphonia.providers.contracts import ProviderAdapter, ProviderObjectRef
from symphonia.providers.importing import CollectionImportResult, ImportIssue, collect_playlist_pages


@dataclass(frozen=True, slots=True)
class ImportPublication:
    state: str
    snapshot: StoredPlaylistSnapshot | None
    retained_current: StoredPlaylistSnapshot | None
    issues: tuple[ImportIssue, ...]


@dataclass(frozen=True, slots=True)
class LibraryImportService:
    projections: PlaylistProjectionRepository

    def import_playlist(
        self,
        adapter: ProviderAdapter,
        *,
        connection_id: str,
        playlist: ProviderObjectRef,
        snapshot_id: str,
        observed_at: datetime,
        cursor: str | None = None,
    ) -> ImportPublication:
        """Read normalized pages through an adapter and publish the result."""

        if adapter.manifest.provider != playlist.provider:
            raise ValueError("adapter provider does not match playlist provider")
        pages = tuple(adapter.read_playlist_pages(connection_id, playlist, cursor))
        result = collect_playlist_pages(pages)
        return self.publish_playlist(result, snapshot_id=snapshot_id, observed_at=observed_at)

    def publish_playlist(
        self,
        result: CollectionImportResult,
        *,
        snapshot_id: str,
        observed_at: datetime,
    ) -> ImportPublication:
        """Publish complete data or retain the prior complete projection."""

        if not result.complete:
            retained = self.projections.current(
                provider=result.provider,
                namespace=result.namespace,
                playlist_id=result.playlist,
            )
            return ImportPublication("partial", None, retained, result.issues)
        snapshot = self.projections.publish(result, snapshot_id=snapshot_id, published_at=observed_at)
        return ImportPublication("succeeded", snapshot, snapshot, result.issues)
