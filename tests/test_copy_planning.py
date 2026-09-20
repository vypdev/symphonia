from __future__ import annotations

import unittest

from symphonia.application import CopyPlanningService
from symphonia.domain import (
    CopyPolicy,
    EntryClassification,
    PlanAcceptanceError,
    PlaylistSnapshot,
    SourcePlaylistEntry,
)


def snapshot(*entries: SourcePlaylistEntry) -> PlaylistSnapshot:
    return PlaylistSnapshot(
        snapshot_id="snapshot-1",
        source_provider="spotify",
        source_playlist_id="playlist-1",
        entries=tuple(entries),
    )


class CopyPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CopyPlanningService()

    def test_strict_plan_preserves_order_and_duplicate_occurrences(self) -> None:
        plan = self.service.plan(
            snapshot(
                SourcePlaylistEntry("occ-1", 0, "sp-1", EntryClassification.READY, "yt-1"),
                SourcePlaylistEntry("occ-2", 1, "sp-1", EntryClassification.READY, "yt-1"),
            ),
            target_provider="youtube",
            target_playlist_name="Rock",
        )

        self.assertFalse(plan.blocked)
        self.assertEqual([entry.occurrence_id for entry in plan.writable_entries], ["occ-1", "occ-2"])
        self.assertEqual([entry.position for entry in plan.writable_entries], [0, 1])
        self.assertEqual(plan.writable_entries[0].target_track_id, plan.writable_entries[1].target_track_id)

    def test_strict_plan_blocks_every_non_ready_entry(self) -> None:
        plan = self.service.plan(
            snapshot(
                SourcePlaylistEntry(
                    "occ-1",
                    0,
                    "sp-1",
                    EntryClassification.AMBIGUOUS,
                    reason="two candidates",
                ),
                SourcePlaylistEntry("occ-2", 1, "sp-2", EntryClassification.UNAVAILABLE),
            ),
            target_provider="youtube",
            target_playlist_name="Rock",
        )

        self.assertTrue(plan.blocked)
        self.assertEqual([entry.disposition for entry in plan.entries], ["blocked", "blocked"])
        with self.assertRaises(PlanAcceptanceError):
            plan.accept(plan.digest)

    def test_best_effort_retains_classification_and_explicitly_omits(self) -> None:
        plan = self.service.plan(
            snapshot(
                SourcePlaylistEntry("occ-1", 0, "sp-1", EntryClassification.READY, "yt-1"),
                SourcePlaylistEntry("occ-2", 1, "sp-2", EntryClassification.UNMATCHED),
            ),
            target_provider="youtube",
            target_playlist_name="Rock",
            policy=CopyPolicy.BEST_EFFORT,
        )

        accepted = plan.accept(plan.digest)
        self.assertEqual(accepted.accepted_digest, plan.digest)
        self.assertEqual(plan.omitted_entries[0].classification, EntryClassification.UNMATCHED)
        self.assertEqual(plan.omitted_entries[0].disposition, "omit")

    def test_acceptance_rejects_a_changed_digest(self) -> None:
        plan = self.service.plan(
            snapshot(SourcePlaylistEntry("occ-1", 0, "sp-1", EntryClassification.READY, "yt-1")),
            target_provider="youtube",
            target_playlist_name="Rock",
        )
        with self.assertRaises(PlanAcceptanceError):
            plan.accept("not-the-plan")

    def test_snapshot_rejects_duplicate_positions(self) -> None:
        with self.assertRaises(ValueError):
            snapshot(
                SourcePlaylistEntry("occ-1", 0, "sp-1", EntryClassification.READY, "yt-1"),
                SourcePlaylistEntry("occ-2", 0, "sp-2", EntryClassification.READY, "yt-2"),
            )

    def test_source_namespace_is_part_of_plan_digest(self) -> None:
        first = PlaylistSnapshot(
            "snapshot-1",
            "spotify",
            "playlist-1",
            (SourcePlaylistEntry("occ-1", 0, "sp-1", EntryClassification.READY, "yt-1"),),
            "connection-a",
        )
        second = PlaylistSnapshot(
            "snapshot-1",
            "spotify",
            "playlist-1",
            (SourcePlaylistEntry("occ-1", 0, "sp-1", EntryClassification.READY, "yt-1"),),
            "connection-b",
        )
        first_plan = self.service.plan(first, target_provider="youtube", target_playlist_name="Rock")
        second_plan = self.service.plan(second, target_provider="youtube", target_playlist_name="Rock")
        self.assertNotEqual(first_plan.digest, second_plan.digest)

    def test_source_provider_object_type_is_part_of_plan_digest(self) -> None:
        track = snapshot(
            SourcePlaylistEntry(
                "occ-1", 0, "same-id", EntryClassification.READY, "target-1", provider_track_object_type="track"
            )
        )
        episode = snapshot(
            SourcePlaylistEntry(
                "occ-1", 0, "same-id", EntryClassification.READY, "target-1", provider_track_object_type="episode"
            )
        )

        track_plan = self.service.plan(track, target_provider="youtube", target_playlist_name="Rock")
        episode_plan = self.service.plan(episode, target_provider="youtube", target_playlist_name="Rock")

        self.assertNotEqual(track_plan.digest, episode_plan.digest)


if __name__ == "__main__":
    unittest.main()
