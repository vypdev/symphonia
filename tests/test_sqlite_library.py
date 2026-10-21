from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import sqlite3
import tempfile
import unittest

from symphonia.domain import EntryClassification, PublishedPlaylistSnapshot
from symphonia.domain.operations import LeaseConflict, OperationPublicationGuard
from symphonia.infrastructure import (
    IncompleteCollectionError,
    OperationRepository,
    PlaylistProjectionRepository,
    SnapshotConflictError,
    StoredPlaylistSnapshot,
)
from symphonia.infrastructure.sqlite_publication_guard import publication_transaction
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
        self.assertIsInstance(stored, PublishedPlaylistSnapshot)
        self.assertIs(StoredPlaylistSnapshot, PublishedPlaylistSnapshot)
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

    def test_snapshot_round_trip_retains_entry_namespace_and_media_kind(self) -> None:
        original = page()
        changed = replace(original.entries[0], track=ProviderObjectRef("spotify", "track", "track-1", "catalog-other"), media_kind=MediaKind.VIDEO)
        result = collect_playlist_pages([replace(original, entries=(changed,))])
        self.repository.publish(result, snapshot_id="mixed-identity", published_at=NOW)
        for stored in (self.repository.get("mixed-identity"), self.repository.current(provider="spotify", namespace="connection-1", playlist_id="playlist-1")):
            self.assertEqual(stored.snapshot.entries[0].provider_track_namespace, "catalog-other")
            self.assertEqual(stored.snapshot.entries[0].media_kind, "video")

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

    def test_late_older_observation_is_retained_without_replacing_current(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/overlap.sqlite3"
            newer, older = PlaylistProjectionRepository(path), PlaylistProjectionRepository(path)
            try:
                result = collect_playlist_pages([page()])
                newer.publish(result, snapshot_id="newer", published_at=NOW + timedelta(minutes=1))
                older.publish(result, snapshot_id="older", published_at=NOW)
                self.assertEqual(newer.current(provider="spotify", namespace="connection-1", playlist_id="playlist-1").snapshot_id, "newer")
                self.assertEqual(older.get("older").published_at, NOW)
            finally:
                newer.close()
                older.close()

    def test_equal_observation_time_does_not_supersede_current(self) -> None:
        result = collect_playlist_pages([page()])
        self.repository.publish(result, snapshot_id="first", published_at=NOW)
        self.repository.publish(result, snapshot_id="equal", published_at=NOW)
        self.assertEqual(self.repository.current(provider="spotify", namespace="connection-1", playlist_id="playlist-1").snapshot_id, "first")

    def test_later_observation_advances_current(self) -> None:
        result = collect_playlist_pages([page()])
        self.repository.publish(result, snapshot_id="first", published_at=NOW)
        self.repository.publish(result, snapshot_id="later", published_at=NOW + timedelta(seconds=1))
        self.assertEqual(self.repository.current(provider="spotify", namespace="connection-1", playlist_id="playlist-1").snapshot_id, "later")

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


class ImportPublicationGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = f"{directory.name}/state.sqlite3"
        self.operations = OperationRepository(self.path)
        self.addCleanup(self.operations.close)
        self.repository = PlaylistProjectionRepository(self.path)
        self.addCleanup(self.repository.close)
        self.other = OperationRepository(self.path)
        self.addCleanup(self.other.close)
        self.other._connection.execute("PRAGMA busy_timeout = 0")
        self.result = collect_playlist_pages([page()])

    def claim(self, operation_id="import"):
        self.operations.create(
            operation_type="import_playlist", operation_id=operation_id,
            idempotency_key=operation_id, payload={}, now=NOW,
        )
        return self.operations.claim(operation_id, worker_id="worker-a", now=NOW)

    def test_invalid_operation_fences_reject_without_leaving_a_transaction(self) -> None:
        for reason in ("cancelled", "expired", "missing", "wrong-worker", "terminal"):
            with self.subTest(reason=reason):
                operation = self.claim(reason)
                operation_id, worker_id, now = operation.operation_id, "worker-a", NOW
                if reason == "cancelled":
                    self.other.cancel(operation_id, now=NOW)
                elif reason == "expired":
                    now += timedelta(seconds=30)
                elif reason == "missing":
                    operation_id = "absent"
                elif reason == "wrong-worker":
                    worker_id = "worker-b"
                else:
                    self.operations.checkpoint(
                        operation_id, worker_id=worker_id, checkpoint={}, now=NOW, state="succeeded",
                    )
                with self.assertRaises(LeaseConflict):
                    self.repository.publish(
                        self.result, snapshot_id=reason, published_at=NOW,
                        operation_guard=OperationPublicationGuard(operation_id, worker_id, lambda: now),
                    )
                self.assertFalse(self.repository._connection.in_transaction)
                with self.assertRaises(KeyError):
                    self.repository.get(reason)

    def test_publication_excludes_cancellation_until_commit(self) -> None:
        operation = self.claim()
        guard = OperationPublicationGuard(operation.operation_id, "worker-a", lambda: NOW)
        with publication_transaction(self.repository._connection, guard):
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                self.other.cancel(operation.operation_id, now=NOW)
            self.assertFalse(self.operations.get(operation.operation_id).cancel_requested)
        self.assertTrue(self.other.cancel(operation.operation_id, now=NOW).cancel_requested)

    def test_clock_is_read_inside_the_publication_transaction(self) -> None:
        operation = self.claim()
        observed = []

        def after_lock():
            observed.append(self.repository._connection.in_transaction)
            return NOW + timedelta(seconds=30)

        with self.assertRaises(LeaseConflict):
            self.repository.publish(
                self.result, snapshot_id="expired-after-lock", published_at=NOW,
                operation_guard=OperationPublicationGuard(operation.operation_id, "worker-a", after_lock),
            )
        self.assertEqual(observed, [True])
        with self.assertRaises(KeyError):
            self.repository.get("expired-after-lock")

    def test_cancelled_idempotent_retry_cannot_bypass_the_guard(self) -> None:
        operation = self.claim()
        self.repository.publish(self.result, snapshot_id="existing", published_at=NOW)
        self.other.cancel(operation.operation_id, now=NOW)
        with self.assertRaises(LeaseConflict):
            self.repository.publish(
                self.result, snapshot_id="existing", published_at=NOW,
                operation_guard=OperationPublicationGuard(operation.operation_id, "worker-a", lambda: NOW),
            )
        self.assertEqual(self.repository.get("existing").snapshot_id, "existing")

    def test_missing_shared_operation_store_fails_closed(self) -> None:
        isolated = PlaylistProjectionRepository()
        self.addCleanup(isolated.close)
        with self.assertRaises(sqlite3.OperationalError):
            isolated.publish(
                self.result, snapshot_id="isolated", published_at=NOW,
                operation_guard=OperationPublicationGuard("import", "worker-a", lambda: NOW),
            )
        with self.assertRaises(KeyError):
            isolated.get("isolated")

    def test_interrupted_publication_rolls_back(self) -> None:
        operation = self.claim()
        guard = OperationPublicationGuard(operation.operation_id, "worker-a", lambda: NOW)
        with self.assertRaises(KeyboardInterrupt):
            with publication_transaction(self.repository._connection, guard):
                raise KeyboardInterrupt()
        self.assertFalse(self.repository._connection.in_transaction)
        self.assertTrue(self.other.cancel(operation.operation_id, now=NOW).cancel_requested)


if __name__ == "__main__":
    unittest.main()
