"""Persisted progress must be safe to resume before a provider is contacted."""

from __future__ import annotations

import unittest

from symphonia.application.copy_checkpoint import CopyProgress, parse_copy_progress
from symphonia.application.copy_planning import CopyPlanningService
from symphonia.domain import EntryClassification, PlaylistSnapshot, SourcePlaylistEntry


class CopyCheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        source = PlaylistSnapshot(
            "snapshot-1", "spotify", "playlist-1",
            (
                SourcePlaylistEntry("occ-1", 0, "source-1", EntryClassification.READY, "target-1"),
                SourcePlaylistEntry("occ-2", 1, "source-2", EntryClassification.READY, "target-2"),
            ),
        )
        self.plan = CopyPlanningService().plan(
            source, target_provider="youtube", target_playlist_name="Copy"
        )

    def test_valid_checkpoint_preserves_progress_and_does_not_mutate_input(self) -> None:
        checkpoint = {
            "target_playlist_id": "target-playlist",
            "confirmed_occurrences": ["occ-1"],
            "unknown_step": "occ-2",
        }
        parsed = parse_copy_progress(self.plan, checkpoint)
        self.assertIsInstance(parsed, CopyProgress)
        assert isinstance(parsed, CopyProgress)
        self.assertEqual(parsed.confirmed, ["occ-1"])
        self.assertEqual(parsed.unknown_step, "occ-2")
        parsed.confirmed.append("occ-2")
        self.assertEqual(checkpoint["confirmed_occurrences"], ["occ-1"])

    def test_gapped_or_conflicting_progress_requires_recovery(self) -> None:
        self.assertEqual(
            parse_copy_progress(self.plan, {
                "target_playlist_id": "target-playlist",
                "confirmed_occurrences": ["occ-2"],
            }),
            "invalid_copy_checkpoint",
        )
        self.assertEqual(
            parse_copy_progress(self.plan, {
                "target_playlist_id": "target-playlist",
                "confirmed_occurrences": ["occ-1"],
                "issues": [{"step": "occ-1"}],
            }),
            "invalid_copy_checkpoint",
        )


if __name__ == "__main__":
    unittest.main()
