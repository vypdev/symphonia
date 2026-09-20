from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from symphonia.application import CopyExecutionService, CopyPlanningService, CopyWorkflowService
from symphonia.domain import CopyPolicy, EntryClassification, PlaylistSnapshot, SourcePlaylistEntry
from symphonia.infrastructure import CopyPlanRepository, OperationRepository
from symphonia.providers import TargetPlaylist, WriteOutcome, WriteResult


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


class FakeWriter:
    def __init__(self) -> None:
        self.target = TargetPlaylist("target-playlist-1")
        self.added: list[tuple[str, str]] = []
        self.results: dict[str, WriteResult] = {}
        self.reconcile_results: dict[str, bool] = {}
        self.reconciled: list[str] = []

    def ensure_target_playlist(self, *, provider: str, name: str, visibility: str, idempotency_key: str) -> TargetPlaylist:
        return self.target

    def add_entry(self, *, target_playlist_id: str, provider_track_id: str, idempotency_key: str) -> WriteResult:
        self.added.append((idempotency_key, provider_track_id))
        return self.results.get(idempotency_key, WriteResult(WriteOutcome.CONFIRMED_SUCCESS))

    def reconcile_target_playlist(self, *, idempotency_key: str) -> TargetPlaylist | None:
        return self.target

    def reconcile_entry(self, *, target_playlist_id: str, provider_track_id: str, idempotency_key: str) -> bool:
        self.reconciled.append(idempotency_key)
        return self.reconcile_results.get(idempotency_key, False)


class CopyExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plans = CopyPlanRepository()
        self.operations = OperationRepository()
        self.workflow = CopyWorkflowService(CopyPlanningService(), self.plans, self.operations)
        self.executor = CopyExecutionService(self.plans, self.operations, retry_delay_seconds=30)
        self.writer = FakeWriter()

    def tearDown(self) -> None:
        self.plans.close()
        self.operations.close()

    def snapshot(self, *, policy: CopyPolicy = CopyPolicy.STRICT, include_unmatched: bool = False) -> tuple[object, CopyPolicy]:
        entries = [SourcePlaylistEntry("occ-1", 0, "source-1", EntryClassification.READY, "target-1")]
        if include_unmatched:
            entries.append(SourcePlaylistEntry("occ-2", 1, "source-2", EntryClassification.UNMATCHED))
        source = PlaylistSnapshot("snapshot-1", "spotify", "playlist-1", tuple(entries))
        return source, policy

    def accepted_digest(self, *, policy: CopyPolicy = CopyPolicy.STRICT, include_unmatched: bool = False) -> str:
        source, policy = self.snapshot(policy=policy, include_unmatched=include_unmatched)
        stored = self.workflow.create_plan(
            source,
            target_provider="youtube",
            target_playlist_name="Rock",
            target_visibility="private",
            policy=policy,
            now=NOW,
        )
        return self.workflow.accept_plan(stored.plan.digest, now=NOW).plan.digest

    def test_success_checkpoints_entries_in_source_order(self) -> None:
        digest = self.accepted_digest()
        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-a", now=NOW)
        self.assertEqual(operation.state, "succeeded")
        self.assertEqual([track for _, track in self.writer.added], ["target-1"])
        self.assertEqual(operation.checkpoint["confirmed_occurrences"], ["occ-1"])

    def test_best_effort_omission_is_partial_not_success(self) -> None:
        digest = self.accepted_digest(policy=CopyPolicy.BEST_EFFORT, include_unmatched=True)
        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-a", now=NOW)
        self.assertEqual(operation.state, "partial")
        self.assertEqual(operation.checkpoint["omitted_occurrences"], ["occ-2"])

    def test_unknown_write_is_reconciled_before_success(self) -> None:
        digest = self.accepted_digest()
        step_key = f"{digest}:entry:occ-1"
        self.writer.results[step_key] = WriteResult(WriteOutcome.UNKNOWN_OUTCOME, detail="timeout after request")
        self.writer.reconcile_results[step_key] = True

        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-a", now=NOW)
        self.assertEqual(operation.state, "succeeded")
        self.assertEqual(self.writer.reconciled, [step_key])

    def test_unknown_write_without_reconciliation_requires_user(self) -> None:
        digest = self.accepted_digest()
        step_key = f"{digest}:entry:occ-1"
        self.writer.results[step_key] = WriteResult(WriteOutcome.UNKNOWN_OUTCOME, detail="provider timeout")
        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-a", now=NOW)
        self.assertEqual(operation.state, "waiting_user")
        self.assertEqual(operation.checkpoint["unknown_step"], "occ-1")

        self.operations.resume(operation.operation_id, now=NOW + timedelta(seconds=1))
        self.writer.results[step_key] = WriteResult(WriteOutcome.CONFIRMED_SUCCESS)
        resumed = self.executor.execute(
            digest,
            writer=self.writer,
            worker_id="worker-b",
            now=NOW + timedelta(seconds=1),
        )
        self.assertEqual(resumed.state, "succeeded")

    def test_retryable_write_releases_operation_until_scheduled(self) -> None:
        digest = self.accepted_digest()
        step_key = f"{digest}:entry:occ-1"
        self.writer.results[step_key] = WriteResult(WriteOutcome.RETRYABLE, provider_code="429")
        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-a", now=NOW)
        self.assertEqual(operation.state, "retry_scheduled")
        self.assertEqual(operation.next_run_at, NOW + timedelta(seconds=30))

    def test_rate_limited_write_waits_until_provider_deadline(self) -> None:
        digest = self.accepted_digest()
        step_key = f"{digest}:entry:occ-1"
        self.writer.results[step_key] = WriteResult(
            WriteOutcome.RATE_LIMITED,
            provider_code="429",
            retry_at=NOW + timedelta(minutes=2),
        )

        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-a", now=NOW)
        self.assertEqual(operation.state, "waiting_rate_limit")
        self.assertEqual(operation.next_run_at, NOW + timedelta(minutes=2))


if __name__ == "__main__":
    unittest.main()
