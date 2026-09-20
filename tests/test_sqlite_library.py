from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.domain import EntryClassification
from symphonia.infrastructure import IncompleteCollectionError, PlaylistProjectionRepository
from symphonia.providers import (
    MediaKind,
    ProviderObjectRef,
    ProviderPlaylistEntry,
    ProviderPlaylistPage,
    collect_playlist_pages,
)


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def page(*, namespace: str = "connection-1", complete: bool = True, available: bool = True):
    playlist = ProviderObjectRef("spotify", "playlist", "playlist-1", namespace)
    track = ProviderObjectRef("spotify", "track", "track-1", namespace)
    item = ProviderPlaylistEntry("occ-1", 0, track, MediaKind.TRACK, available=available)
    return ProviderPlaylistPage(playlist, (item,), None, None, complete, revision="rev-1")


class PlaylistProjectionRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = PlaylistProjectionRepository()

    def tearDown(self) -> None:
        self.repository.close()

    def test_complete_result_is_published_with_namespace_and_availability(self) -> None:
        result = collect_playlist_pages([page(available=False)])
        stored = self.repository.publish(result, snapshot_id="snapshot-1", published_at=NOW)
        current = self.repository.current(provider="spotify", namespace="connection-1", playlist_id="playlist-1")
        self.assertEqual(stored.snapshot_id, "snapshot-1")
        self.assertEqual(current.snapshot.source_namespace, "connection-1")
        self.assertEqual(current.snapshot.entries[0].classification, EntryClassification.UNAVAILABLE)

    def test_incomplete_result_cannot_replace_current_projection(self) -> None:
        complete = collect_playlist_pages([page()])
        self.repository.publish(complete, snapshot_id="snapshot-1", published_at=NOW)
        incomplete = collect_playlist_pages([page(complete=False)])
        with self.assertRaises(IncompleteCollectionError):
            self.repository.publish(incomplete, snapshot_id="snapshot-2", published_at=NOW)
        current = self.repository.current(provider="spotify", namespace="connection-1", playlist_id="playlist-1")
        self.assertEqual(current.snapshot_id, "snapshot-1")

    def test_same_external_playlist_id_isolated_by_namespace(self) -> None:
        first = collect_playlist_pages([page(namespace="connection-1")])
        second = collect_playlist_pages([page(namespace="connection-2")])
        self.repository.publish(first, snapshot_id="snapshot-1", published_at=NOW)
        self.repository.publish(second, snapshot_id="snapshot-2", published_at=NOW)
        self.assertEqual(
            self.repository.current(provider="spotify", namespace="connection-1", playlist_id="playlist-1").snapshot_id,
            "snapshot-1",
        )
        self.assertEqual(
            self.repository.current(provider="spotify", namespace="connection-2", playlist_id="playlist-1").snapshot_id,
            "snapshot-2",
        )


if __name__ == "__main__":
    unittest.main()

