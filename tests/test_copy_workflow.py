from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.application import CapabilityUnavailableError, CopyPlanningService, CopyWorkflowService
from symphonia.domain import CopyPolicy, EntryClassification, PlanAcceptanceError, PlaylistSnapshot, SourcePlaylistEntry
from symphonia.infrastructure import CopyPlanRepository, OperationRepository
from symphonia.providers import Capability, ProviderCapabilities


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

    def test_plan_binds_target_connection_and_capability_evidence(self) -> None:
        capabilities = ProviderCapabilities(
            enabled=frozenset({Capability.CREATE_PLAYLIST, Capability.ADD_PLAYLIST_ENTRIES}),
            evidence_version="probe-spotify-1",
            observed_at="2026-09-20T12:00:00Z",
        )
        stored = self.workflow.create_plan(
            self.snapshot(),
            target_provider="spotify",
            target_playlist_name="Rock",
            target_visibility="private",
            policy=CopyPolicy.STRICT,
            target_connection_id="spotify-connection-2",
            target_capabilities=capabilities,
            now=self.now,
        )
        self.assertEqual(stored.plan.target_connection_id, "spotify-connection-2")
        self.assertEqual(
            stored.plan.target_capabilities,
            ("add_playlist_entries", "create_playlist"),
        )
        self.assertEqual(stored.plan.target_capability_evidence_version, "probe-spotify-1")
        reloaded = self.plans.get(stored.plan.digest)
        self.assertEqual(reloaded.plan, stored.plan)

    def test_plan_rejects_target_without_required_write_capabilities(self) -> None:
        with self.assertRaises(CapabilityUnavailableError):
            self.workflow.create_plan(
                self.snapshot(),
                target_provider="spotify",
                target_playlist_name="Rock",
                target_visibility="private",
                policy=CopyPolicy.STRICT,
                target_connection_id="spotify-connection-2",
                target_capabilities=ProviderCapabilities(
                    enabled=frozenset({Capability.READ_PLAYLISTS}),
                    evidence_version="probe-spotify-1",
                    observed_at="2026-09-20T12:00:00Z",
                ),
                now=self.now,
            )


if __name__ == "__main__":
    unittest.main()
