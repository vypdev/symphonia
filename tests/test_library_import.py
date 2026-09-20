from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.application import LibraryImportService
from symphonia.infrastructure import PlaylistProjectionRepository
from symphonia.providers import (
    MediaKind,
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


if __name__ == "__main__":
    unittest.main()

