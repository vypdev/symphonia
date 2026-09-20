"""Application use case for publishing normalized playlist imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from symphonia.infrastructure.sqlite_library import PlaylistProjectionRepository, StoredPlaylistSnapshot
from symphonia.providers.importing import CollectionImportResult, ImportIssue


@dataclass(frozen=True, slots=True)
class ImportPublication:
    state: str
    snapshot: StoredPlaylistSnapshot | None
    retained_current: StoredPlaylistSnapshot | None
    issues: tuple[ImportIssue, ...]


@dataclass(frozen=True, slots=True)
class LibraryImportService:
    projections: PlaylistProjectionRepository

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

