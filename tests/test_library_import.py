from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.application import LibraryImportService
from symphonia.infrastructure import PlaylistProjectionRepository
from symphonia.providers import (
    AccessBasis,
    MediaKind,
    ProviderCapabilities,
    ProviderManifest,
    ProviderObjectRef,
    ProviderPlaylistEntry,
    ProviderPlaylistPage,
    collect_playlist_pages,
)


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def result(complete: bool):
    playlist = ProviderObjectRef("spotify", "playlist", "playlist-1", "connection-1")
    track = ProviderObjectRef("spotify", "track", "track-1", "connection-1")
    item = ProviderPlaylistEntry("occ-1", 0, track, MediaKind.TRACK)
    return collect_playlist_pages([ProviderPlaylistPage(playlist, (item,), None, None, complete)])


class LibraryImportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = PlaylistProjectionRepository()
        self.service = LibraryImportService(self.repository)

    def tearDown(self) -> None:
        self.repository.close()

    def test_complete_import_publishes_snapshot(self) -> None:
        publication = self.service.publish_playlist(result(True), snapshot_id="snapshot-1", observed_at=NOW)
        self.assertEqual(publication.state, "succeeded")
        self.assertEqual(publication.snapshot.snapshot_id, "snapshot-1")
        self.assertEqual(publication.retained_current.snapshot_id, "snapshot-1")

    def test_partial_import_retains_last_complete_snapshot(self) -> None:
        self.service.publish_playlist(result(True), snapshot_id="snapshot-1", observed_at=NOW)
        publication = self.service.publish_playlist(result(False), snapshot_id="snapshot-2", observed_at=NOW)
        self.assertEqual(publication.state, "partial")
        self.assertIsNone(publication.snapshot)
        self.assertEqual(publication.retained_current.snapshot_id, "snapshot-1")

    def test_import_playlist_uses_normalized_adapter_pages(self) -> None:
        playlist = ProviderObjectRef("spotify", "playlist", "playlist-1", "connection-1")

        class FakeAdapter:
            manifest = ProviderManifest("spotify", "Spotify", AccessBasis.OFFICIAL, "beta", "limited")

            def capabilities(self, connection_id: str) -> ProviderCapabilities:
                return ProviderCapabilities(frozenset(), "fixture", "2026-09-20T12:00:00Z")

            def read_playlist_pages(self, connection_id: str, requested: ProviderObjectRef, cursor: str | None = None):
                self.assert_connection = connection_id
                return [
                    ProviderPlaylistPage(
                        requested,
                        (ProviderPlaylistEntry("occ-1", 0, ProviderObjectRef("spotify", "track", "track-1", requested.namespace), MediaKind.TRACK),),
                        cursor,
                        None,
                        True,
                    )
                ]

        publication = self.service.import_playlist(
            FakeAdapter(),
            connection_id="connection-1",
            playlist=playlist,
            snapshot_id="snapshot-adapter",
            observed_at=NOW,
        )
        self.assertEqual(publication.state, "succeeded")
        self.assertEqual(publication.snapshot.snapshot_id, "snapshot-adapter")

    def test_import_playlist_rejects_another_provider_adapter(self) -> None:
        playlist = ProviderObjectRef("spotify", "playlist", "playlist-1", "connection-1")

        class WrongAdapter:
            manifest = ProviderManifest("youtube", "YouTube", AccessBasis.OFFICIAL, "beta", "limited")

            def read_playlist_pages(self, connection_id: str, requested: ProviderObjectRef, cursor: str | None = None):
                return ()

        with self.assertRaises(ValueError):
            self.service.import_playlist(
                WrongAdapter(),
                connection_id="connection-1",
                playlist=playlist,
                snapshot_id="snapshot-wrong",
                observed_at=NOW,
            )


if __name__ == "__main__":
    unittest.main()
