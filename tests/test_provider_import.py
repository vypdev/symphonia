from __future__ import annotations

from datetime import date
import unittest

from symphonia.domain import EntryClassification
from symphonia.providers import (
    AccessBasis,
    ImportIssue,
    MediaKind,
    ProviderManifest,
    ProviderObjectRef,
    ProviderPlaylistEntry,
    ProviderPlaylistPage,
    ProviderAlreadyRegistered,
    ProviderNotRegistered,
    ProviderRegistry,
    AppleMusicAdapter,
    SpotifyAdapter,
    YouTubeDataAdapter,
    collect_playlist_pages,
    to_playlist_snapshot,
)


def playlist_ref(provider: str = "spotify") -> ProviderObjectRef:
    return ProviderObjectRef(provider, "playlist", "playlist-1", "connection-1")


def entry(occurrence_id: str, position: int, track_id: str, available: bool = True) -> ProviderPlaylistEntry:
    return ProviderPlaylistEntry(
        occurrence_id=occurrence_id,
        position=position,
        track=ProviderObjectRef("spotify", "track", track_id, "connection-1"),
        media_kind=MediaKind.TRACK,
        available=available,
    )


class ProviderContractTests(unittest.TestCase):
    def test_provider_registry_discovers_sorted_manifests_and_rejects_duplicates(self) -> None:
        class FakeAdapter:
            def __init__(self, provider: str) -> None:
                self.manifest = ProviderManifest(provider, provider.title(), AccessBasis.OFFICIAL, "beta", "limited")

            def capabilities(self, connection_id: str):
                raise NotImplementedError

            def read_playlist_pages(self, connection_id: str, playlist: ProviderObjectRef, cursor: str | None = None):
                raise NotImplementedError

        registry = ProviderRegistry()
        registry.register(FakeAdapter("youtube"))
        registry.register(FakeAdapter("spotify"))
        self.assertEqual([manifest.provider for manifest in registry.manifests()], ["spotify", "youtube"])
        with self.assertRaises(ProviderAlreadyRegistered):
            registry.register(FakeAdapter("spotify"))
        with self.assertRaises(ProviderNotRegistered):
            registry.get("apple")

    def test_external_identity_is_namespaced_by_type_and_connection(self) -> None:
        same_upstream_id = ProviderObjectRef("spotify", "track", "same", "connection-a")
        another_connection = ProviderObjectRef("spotify", "track", "same", "connection-b")
        another_type = ProviderObjectRef("spotify", "video", "same", "connection-a")
        self.assertNotEqual(same_upstream_id.external_key, another_connection.external_key)
        self.assertNotEqual(same_upstream_id.external_key, another_type.external_key)

    def test_normalized_provider_values_reject_non_textual_identity_fields(self) -> None:
        with self.assertRaises(ValueError):
            ProviderObjectRef(None, "track", "track-1", "connection-1")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ProviderPlaylistEntry(
                occurrence_id=None,  # type: ignore[arg-type]
                position=0,
                track=ProviderObjectRef("spotify", "track", "track-1", "connection-1"),
                media_kind=MediaKind.TRACK,
            )
        with self.assertRaises(ValueError):
            ProviderPlaylistPage(
                playlist_ref(),
                (),
                None,
                None,
                True,
                revision=42,  # type: ignore[arg-type]
            )

    def test_normalized_provider_values_reject_wrong_runtime_types(self) -> None:
        with self.assertRaises(ValueError):
            ProviderManifest("spotify", "Spotify", "official", "beta", "limited")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ProviderPlaylistEntry(
                occurrence_id="occ-1",
                position=True,  # type: ignore[arg-type]
                track=ProviderObjectRef("spotify", "track", "track-1", "connection-1"),
                media_kind=MediaKind.TRACK,
            )
        with self.assertRaises(ValueError):
            ProviderPlaylistEntry(
                occurrence_id="occ-1",
                position=0,
                track=None,  # type: ignore[arg-type]
                media_kind=MediaKind.TRACK,
            )
        with self.assertRaises(ValueError):
            ProviderPlaylistEntry(
                occurrence_id="occ-1",
                position=0,
                track=ProviderObjectRef("spotify", "track", "track-1", "connection-1"),
                media_kind="track",  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            ProviderPlaylistPage(playlist_ref(), [], None, None, True)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ProviderPlaylistPage(
                playlist_ref(),
                (entry("occ-1", 0, "track-1"), entry("occ-2", 0, "track-2")),
                None,
                None,
                True,
            )

    def test_manifest_discloses_access_basis(self) -> None:
        manifest = ProviderManifest("spotify", "Spotify", AccessBasis.OFFICIAL, "beta", "limited")
        self.assertEqual(manifest.access_basis, AccessBasis.OFFICIAL)
        with self.assertRaises(ValueError):
            ProviderManifest(
                "spotify",
                "Spotify",
                AccessBasis.OFFICIAL,
                "beta",
                "limited",
                reviewed_on="2026-9-2",
            )

    def test_concrete_adapter_manifests_have_dated_provenance(self) -> None:
        for adapter in (SpotifyAdapter, YouTubeDataAdapter, AppleMusicAdapter):
            manifest = adapter.manifest
            self.assertTrue(manifest.upstream_dependencies)
            self.assertIsNotNone(manifest.reviewed_on)
            date.fromisoformat(manifest.reviewed_on or "")

    def test_complete_pages_preserve_order_and_duplicate_occurrences(self) -> None:
        result = collect_playlist_pages(
            [
                ProviderPlaylistPage(playlist_ref(), (entry("occ-1", 0, "track-1"),), None, "cursor-2", False),
                ProviderPlaylistPage(
                    playlist_ref(),
                    (entry("occ-2", 1, "track-1"), entry("occ-3", 2, "track-2")),
                    "cursor-2",
                    None,
                    True,
                ),
            ]
        )
        self.assertTrue(result.complete)
        self.assertEqual([item.occurrence_id for item in result.entries], ["occ-1", "occ-2", "occ-3"])
        self.assertEqual(result.entries[0].track.object_id, result.entries[1].track.object_id)

    def test_incomplete_page_does_not_look_complete(self) -> None:
        result = collect_playlist_pages(
            [ProviderPlaylistPage(playlist_ref(), (entry("occ-1", 0, "track-1"),), None, "cursor-2", False)]
        )
        self.assertFalse(result.complete)
        self.assertEqual(result.issues, (ImportIssue.MISSING_CONTINUATION,))

    def test_repeated_cursor_and_conflicting_occurrence_are_incomplete(self) -> None:
        first = ProviderPlaylistPage(playlist_ref(), (entry("occ-1", 0, "track-1"),), None, "cursor-2", False)
        second = ProviderPlaylistPage(playlist_ref(), (entry("occ-1", 0, "track-other"),), "cursor-2", "cursor-2", False)
        result = collect_playlist_pages([first, second])
        self.assertFalse(result.complete)
        self.assertIn(ImportIssue.CONFLICTING_OCCURRENCE, result.issues)
        self.assertIn(ImportIssue.REPEATED_CURSOR, result.issues)

    def test_snapshot_keeps_unavailable_entries_visible(self) -> None:
        result = collect_playlist_pages(
            [ProviderPlaylistPage(playlist_ref(), (entry("occ-1", 0, "track-1", False),), None, None, True)]
        )
        snapshot = to_playlist_snapshot(result, "snapshot-1")
        self.assertEqual(snapshot.entries[0].classification, EntryClassification.UNAVAILABLE)
        self.assertEqual(snapshot.entries[0].occurrence_id, "occ-1")
        self.assertEqual(snapshot.source_namespace, "connection-1")


if __name__ == "__main__":
    unittest.main()
