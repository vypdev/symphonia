"""Application use case for publishing normalized playlist imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from symphonia.domain.operations import OperationPublicationGuard
from symphonia.domain.projections import PublishedPlaylistSnapshot
from symphonia.providers.contracts import ProviderAdapter, ProviderObjectRef
from symphonia.providers.importing import CollectionImportResult, ImportIssue, collect_playlist_pages

from .ports import PlaylistProjectionPort


@dataclass(frozen=True, slots=True)
class ImportPublication:
    state: str
    snapshot: PublishedPlaylistSnapshot | None
    retained_current: PublishedPlaylistSnapshot | None
    issues: tuple[ImportIssue, ...]


@dataclass(frozen=True, slots=True)
class LibraryImportService:
    projections: PlaylistProjectionPort

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

        result = self.collect_playlist(
            adapter, connection_id=connection_id, playlist=playlist, cursor=cursor,
        )
        return self.publish_playlist(result, snapshot_id=snapshot_id, observed_at=observed_at)

    def collect_playlist(
        self,
        adapter: ProviderAdapter,
        *,
        connection_id: str,
        playlist: ProviderObjectRef,
        cursor: str | None = None,
    ) -> CollectionImportResult:
        """Collect normalized pages without changing the current projection."""

        if adapter.manifest.provider != playlist.provider:
            raise ValueError("adapter provider does not match playlist provider")
        pages = tuple(adapter.read_playlist_pages(connection_id, playlist, cursor))
        return collect_playlist_pages(pages)

    def publish_playlist(
        self,
        result: CollectionImportResult,
        *,
        snapshot_id: str,
        observed_at: datetime,
        operation_guard: OperationPublicationGuard | None = None,
    ) -> ImportPublication:
        """Publish complete data or retain the prior complete projection."""

        if not result.complete:
            retained = self.projections.current(
                provider=result.provider,
                namespace=result.namespace,
                playlist_id=result.playlist,
            )
            return ImportPublication("partial", None, retained, result.issues)
        snapshot = self.projections.publish(
            result, snapshot_id=snapshot_id, published_at=observed_at,
            operation_guard=operation_guard,
        )
        current = self.projections.current(
            provider=result.provider, namespace=result.namespace, playlist_id=result.playlist,
        )
        return ImportPublication("succeeded", snapshot, current, result.issues)
