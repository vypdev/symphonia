"""Application use case for publishing normalized playlist imports."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from datetime import datetime

from symphonia.domain.operations import OperationPublicationGuard
from symphonia.domain.projections import PublishedPlaylistSnapshot
from symphonia.providers.contracts import ProviderAdapter, ProviderObjectRef
from symphonia.providers.errors import ProviderApiError, ProviderErrorCategory
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
        before_page: Callable[[], None] | None = None,
    ) -> CollectionImportResult:
        """Collect normalized pages without changing the current projection."""

        if adapter.manifest.provider != playlist.provider:
            raise ValueError("adapter provider does not match playlist provider")
        if before_page is not None:
            before_page()
        reader = getattr(adapter, "iter_playlist_pages", adapter.read_playlist_pages)
        stream = iter(reader(connection_id, playlist, cursor))
        pages = []
        failure: BaseException | None = None
        try:
            while True:
                if before_page is not None:
                    before_page()
                try:
                    pages.append(next(stream))
                except StopIteration:
                    break
        except BaseException as error:
            failure = error
            raise
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except BaseException:
                    if failure is None:
                        raise
        if any(page.playlist.external_key != playlist.external_key for page in pages):
            raise ProviderApiError(
                ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED,
                "Provider pages do not match the requested playlist identity",
            )
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
