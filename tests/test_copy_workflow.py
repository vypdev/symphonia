from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.application import CopyPlanningService, CopyWorkflowService
from symphonia.domain import CopyPolicy, EntryClassification, PlanAcceptanceError, PlaylistSnapshot, SourcePlaylistEntry
from symphonia.infrastructure import CopyPlanRepository, OperationRepository


class CopyWorkflowTests(unittest.TestCase):
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)

    def setUp(self) -> None:
        self.plans = CopyPlanRepository()
        self.operations = OperationRepository()
        self.workflow = CopyWorkflowService(CopyPlanningService(), self.plans, self.operations)

    def tearDown(self) -> None:
        self.plans.close()
        self.operations.close()

    def snapshot(self, classification: EntryClassification = EntryClassification.READY) -> PlaylistSnapshot:
        return PlaylistSnapshot(
            snapshot_id="snapshot-1",
            source_provider="spotify",
            source_playlist_id="playlist-1",
            entries=(
                SourcePlaylistEntry(
                    "occ-1",
                    0,
                    "spotify-track-1",
                    classification,
                    "youtube-track-1" if classification is EntryClassification.READY else None,
                ),
            ),
        )

    def test_workflow_requires_acceptance_before_enqueue(self) -> None:
        stored = self.workflow.create_plan(
            self.snapshot(),
            target_provider="youtube",
            target_playlist_name="Rock",
            target_visibility="private",
            policy=CopyPolicy.STRICT,
            now=self.now,
        )
        with self.assertRaises(PlanAcceptanceError):
            self.workflow.enqueue_accepted_plan(stored.plan.digest, now=self.now)

    def test_workflow_accepts_then_enqueues_idempotently(self) -> None:
        stored = self.workflow.create_plan(
            self.snapshot(),
            target_provider="youtube",
            target_playlist_name="Rock",
            target_visibility="private",
            policy=CopyPolicy.STRICT,
            now=self.now,
        )
        accepted = self.workflow.accept_plan(stored.plan.digest, now=self.now)
        operation = self.workflow.enqueue_accepted_plan(accepted.plan.digest, now=self.now)
        duplicate = self.workflow.enqueue_accepted_plan(accepted.plan.digest, now=self.now)
        self.assertEqual(operation.operation_id, duplicate.operation_id)
        self.assertEqual(operation.state, "queued")
        self.assertEqual(operation.payload, {"plan_digest": accepted.plan.digest})

    def test_blocked_plan_cannot_be_accepted(self) -> None:
        stored = self.workflow.create_plan(
            self.snapshot(EntryClassification.AMBIGUOUS),
            target_provider="youtube",
            target_playlist_name="Rock",
            target_visibility="private",
            policy=CopyPolicy.STRICT,
            now=self.now,
        )
        with self.assertRaises(PlanAcceptanceError):
            self.workflow.accept_plan(stored.plan.digest, now=self.now)


if __name__ == "__main__":
    unittest.main()

