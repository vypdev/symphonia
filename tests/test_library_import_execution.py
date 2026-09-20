from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.application import LibraryImportExecutionService, LibraryImportService, OperationRunner
from symphonia.infrastructure import OperationRepository, PlaylistProjectionRepository
from symphonia.providers import (
    AccessBasis,
    ProviderApiError,
    ProviderErrorCategory,
    ProviderManifest,
    ProviderObjectRef,
    ProviderPlaylistEntry,
    ProviderPlaylistPage,
    MediaKind,
)


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


class FakeAdapter:
    manifest = ProviderManifest("spotify", "Spotify", AccessBasis.OFFICIAL, "beta", "read")

    def __init__(self, *, error: ProviderApiError | None = None, complete: bool = True) -> None:
        self.error = error
        self.complete = complete

    def capabilities(self, connection_id: str):
        raise AssertionError("not used")

    def read_playlist_pages(self, connection_id: str, playlist: ProviderObjectRef, cursor: str | None = None):
        if self.error is not None:
            raise self.error
        entry = ProviderPlaylistEntry(
            "occ-1",
            0,
            ProviderObjectRef("spotify", "track", "track-1", playlist.namespace),
            MediaKind.TRACK,
        )
        return (ProviderPlaylistPage(playlist, (entry,), cursor, None, self.complete),)


class LibraryImportExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.operations = OperationRepository()
        self.projections = PlaylistProjectionRepository()
        self.service = LibraryImportExecutionService(LibraryImportService(self.projections), self.operations)
        self.playlist = ProviderObjectRef("spotify", "playlist", "playlist-1", "connection-1")

    def tearDown(self) -> None:
        self.projections.close()
        self.operations.close()

    def enqueue(self, adapter: FakeAdapter) -> object:
        operation = self.service.enqueue_playlist(
            adapter,
            connection_id="connection-1",
            playlist=self.playlist,
            snapshot_id="snapshot-1",
            observed_at=NOW,
            now=NOW,
        )
        runner = OperationRunner(
            self.operations,
            {
                "import_playlist": lambda claimed, worker_id, now: self.service.execute_claimed(
                    claimed,
                    adapter=adapter,
                    worker_id=worker_id,
                    now=now,
                )
            },
        )
        return runner.run_once(worker_id="worker-a", now=NOW)

    def test_import_is_published_as_a_succeeded_operation(self) -> None:
        result = self.enqueue(FakeAdapter())
        self.assertEqual(result.state, "succeeded")
        self.assertEqual(result.checkpoint["published_snapshot_id"], "snapshot-1")

    def test_provider_auth_failure_waits_for_user_without_leaking_detail(self) -> None:
        result = self.enqueue(
            FakeAdapter(error=ProviderApiError(ProviderErrorCategory.AUTHENTICATION_REQUIRED, "token=secret"))
        )
        self.assertEqual(result.state, "waiting_user")
        self.assertEqual(result.checkpoint["failure_code"], "authentication_required")
        self.assertNotIn("secret", str(result.checkpoint))

    def test_incomplete_import_is_partial_and_retains_no_new_snapshot(self) -> None:
        result = self.enqueue(FakeAdapter(complete=False))
        self.assertEqual(result.state, "partial")
        self.assertIsNone(result.checkpoint["published_snapshot_id"])
        self.assertEqual(result.checkpoint["publication_state"], "partial")


if __name__ == "__main__":
    unittest.main()
