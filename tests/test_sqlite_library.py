from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
import tempfile
import unittest

from symphonia.domain import EntryClassification
from symphonia.infrastructure import (
    IncompleteCollectionError,
    PlaylistProjectionRepository,
    SnapshotConflictError,
)
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

    def test_complete_result_retains_provider_metadata_for_future_resolution(self) -> None:
        playlist = ProviderObjectRef("spotify", "playlist", "playlist-1", "connection-1")
        track = ProviderObjectRef("spotify", "track", "track-1", "connection-1")
        item = ProviderPlaylistEntry(
            "occ-1",
            0,
            track,
            MediaKind.TRACK,
            title="Song title",
            source_added_at="2026-09-20T12:00:00Z",
        )
        result = collect_playlist_pages([ProviderPlaylistPage(playlist, (item,), None, None, True)])

        stored = self.repository.publish(result, snapshot_id="snapshot-metadata", published_at=NOW)

        self.assertEqual(stored.snapshot.entries[0].provider_track_title, "Song title")
        self.assertEqual(stored.snapshot.entries[0].source_added_at, "2026-09-20T12:00:00Z")

    def test_summary_reports_import_freshness_without_playlist_content(self) -> None:
        self.repository.publish(
            collect_playlist_pages([page(available=False)]),
            snapshot_id="snapshot-summary",
            published_at=NOW,
        )

        summary = self.repository.summary()

        self.assertEqual(summary["snapshot_count"], 1)
        self.assertEqual(summary["current_playlist_count"], 1)
        self.assertEqual(summary["entry_count"], 1)
        self.assertEqual(summary["unavailable_entry_count"], 1)
        self.assertEqual(summary["latest_published_at"], "2026-09-20T12:00:00.000000+00:00")
        self.assertNotIn("playlist-1", str(summary))

    def test_legacy_projection_schema_gets_metadata_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/legacy.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE playlist_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    playlist_id TEXT NOT NULL,
                    revision TEXT,
                    published_at TEXT NOT NULL
                );
                CREATE TABLE playlist_snapshot_entries (
                    snapshot_id TEXT NOT NULL,
                    occurrence_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    provider_track_id TEXT NOT NULL,
                    provider_track_namespace TEXT NOT NULL,
                    media_kind TEXT NOT NULL,
                    available INTEGER NOT NULL
                );
                CREATE TABLE current_playlist_snapshots (
                    provider TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    playlist_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL
                );
                """
            )
            connection.close()

            migrated = PlaylistProjectionRepository(path)
            columns = {
                row[1]
                for row in migrated._connection.execute("PRAGMA table_info(playlist_snapshot_entries)").fetchall()
            }
            migrated.close()

        self.assertIn("provider_track_object_type", columns)
        self.assertIn("provider_track_title", columns)
        self.assertIn("source_added_at", columns)

    def test_incomplete_result_cannot_replace_current_projection(self) -> None:
        complete = collect_playlist_pages([page()])
        self.repository.publish(complete, snapshot_id="snapshot-1", published_at=NOW)
        incomplete = collect_playlist_pages([page(complete=False)])
        with self.assertRaises(IncompleteCollectionError):
            self.repository.publish(incomplete, snapshot_id="snapshot-2", published_at=NOW)
        current = self.repository.current(provider="spotify", namespace="connection-1", playlist_id="playlist-1")
        self.assertEqual(current.snapshot_id, "snapshot-1")

    def test_republishing_same_snapshot_is_idempotent(self) -> None:
        result = collect_playlist_pages([page()])
        first = self.repository.publish(result, snapshot_id="snapshot-1", published_at=NOW)
        second = self.repository.publish(result, snapshot_id="snapshot-1", published_at=NOW.replace(minute=1))
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        count = self.repository._connection.execute("SELECT COUNT(*) FROM playlist_snapshots").fetchone()[0]
        self.assertEqual(count, 1)

        newer = collect_playlist_pages([page(namespace="connection-1")])
        self.repository.publish(newer, snapshot_id="snapshot-2", published_at=NOW.replace(minute=2))
        self.repository.publish(result, snapshot_id="snapshot-1", published_at=NOW.replace(minute=3))
        current = self.repository.current(provider="spotify", namespace="connection-1", playlist_id="playlist-1")
        self.assertEqual(current.snapshot_id, "snapshot-2")

    def test_reusing_snapshot_id_for_different_content_is_rejected(self) -> None:
        self.repository.publish(collect_playlist_pages([page()]), snapshot_id="snapshot-1", published_at=NOW)
        changed = collect_playlist_pages(
            [
                ProviderPlaylistPage(
                    ProviderObjectRef("spotify", "playlist", "playlist-1", "connection-1"),
                    (
                        ProviderPlaylistEntry(
                            "occ-1",
                            0,
                            ProviderObjectRef("spotify", "track", "track-2", "connection-1"),
                            MediaKind.TRACK,
                        ),
                    ),
                    None,
                    None,
                    True,
                    revision="rev-1",
                )
            ]
        )
        with self.assertRaises(SnapshotConflictError):
            self.repository.publish(changed, snapshot_id="snapshot-1", published_at=NOW)

    def test_reusing_snapshot_id_with_different_provider_object_type_is_rejected(self) -> None:
        self.repository.publish(collect_playlist_pages([page()]), snapshot_id="snapshot-1", published_at=NOW)
        changed = collect_playlist_pages(
            [
                ProviderPlaylistPage(
                    ProviderObjectRef("spotify", "playlist", "playlist-1", "connection-1"),
                    (
                        ProviderPlaylistEntry(
                            "occ-1",
                            0,
                            ProviderObjectRef("spotify", "episode", "track-1", "connection-1"),
                            MediaKind.PODCAST,
                        ),
                    ),
                    None,
                    None,
                    True,
                    revision="rev-1",
                )
            ]
        )
        with self.assertRaises(SnapshotConflictError):
            self.repository.publish(changed, snapshot_id="snapshot-1", published_at=NOW)

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
