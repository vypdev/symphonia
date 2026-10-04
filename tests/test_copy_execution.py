from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from symphonia.application import CopyExecutionService, CopyPlanningService, CopyWorkflowService, OperationRunner
from symphonia.domain import CopyPolicy, EntryClassification, PlaylistSnapshot, SourcePlaylistEntry
from symphonia.infrastructure import CopyPlanRepository, OperationRepository
from symphonia.providers import ProviderWriteError, TargetPlaylist, WriteOutcome, WriteResult


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

    def snapshot(
        self,
        *,
        policy: CopyPolicy = CopyPolicy.STRICT,
        include_unmatched: bool = False,
        include_second_ready: bool = False,
    ) -> tuple[PlaylistSnapshot, CopyPolicy]:
        entries = [SourcePlaylistEntry("occ-1", 0, "source-1", EntryClassification.READY, "target-1")]
        if include_second_ready:
            entries.append(SourcePlaylistEntry("occ-2", 1, "source-2", EntryClassification.READY, "target-2"))
        if include_unmatched:
            entries.append(
                SourcePlaylistEntry(f"occ-{len(entries) + 1}", len(entries), "source-3", EntryClassification.UNMATCHED)
            )
        source = PlaylistSnapshot("snapshot-1", "spotify", "playlist-1", tuple(entries))
        return source, policy

    def accepted_digest(
        self,
        *,
        policy: CopyPolicy = CopyPolicy.STRICT,
        include_unmatched: bool = False,
        include_second_ready: bool = False,
    ) -> str:
        source, policy = self.snapshot(
            policy=policy,
            include_unmatched=include_unmatched,
            include_second_ready=include_second_ready,
        )
        stored = self.workflow.create_plan(
            source,
            target_provider="youtube",
            target_playlist_name="Rock",
            target_visibility="private",
            policy=policy,
            now=NOW,
        )
        return self.workflow.accept_plan(stored.plan.digest, now=NOW).plan.digest

    def resume_with_checkpoint(self, digest: str, checkpoint: dict[str, object]) -> None:
        operation = self.operations.create(
            operation_type="copy_playlist",
            idempotency_key=f"copy-plan:{digest}",
            payload={"plan_digest": digest},
            now=NOW,
        )
        self.operations.claim(operation.operation_id, worker_id="seeding-worker", now=NOW)
        self.operations.checkpoint(
            operation.operation_id,
            worker_id="seeding-worker",
            checkpoint=checkpoint,
            now=NOW,
            state="waiting_user",
        )
        self.operations.resume(operation.operation_id, now=NOW + timedelta(seconds=1))

    def test_success_checkpoints_entries_in_source_order(self) -> None:
        digest = self.accepted_digest()
        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-a", now=NOW)
        self.assertEqual(operation.state, "succeeded")
        self.assertEqual([track for _, track in self.writer.added], ["target-1"])
        self.assertEqual(operation.checkpoint["confirmed_occurrences"], ["occ-1"])

    def test_duplicate_target_tracks_keep_distinct_ordered_occurrences(self) -> None:
        source = PlaylistSnapshot(
            "snapshot-duplicates",
            "spotify",
            "playlist-1",
            (
                SourcePlaylistEntry("occ-1", 0, "source-1", EntryClassification.READY, "target-shared"),
                SourcePlaylistEntry("occ-2", 1, "source-1", EntryClassification.READY, "target-shared"),
                SourcePlaylistEntry("occ-3", 2, "source-2", EntryClassification.READY, "target-other"),
            ),
        )
        stored = self.workflow.create_plan(
            source,
            target_provider="youtube",
            target_playlist_name="Duplicates",
            target_visibility="private",
            policy=CopyPolicy.STRICT,
            now=NOW,
        )
        digest = self.workflow.accept_plan(stored.plan.digest, now=NOW).plan.digest

        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-a", now=NOW)

        self.assertEqual(operation.state, "succeeded")
        self.assertEqual(operation.checkpoint["confirmed_occurrences"], ["occ-1", "occ-2", "occ-3"])
        self.assertEqual(
            self.writer.added,
            [
                (f"{digest}:entry:occ-1", "target-shared"),
                (f"{digest}:entry:occ-2", "target-shared"),
                (f"{digest}:entry:occ-3", "target-other"),
            ],
        )

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

    def test_unknown_target_creation_is_not_repeated_until_reconciled(self) -> None:
        class UnknownTargetWriter(FakeWriter):
            def __init__(self) -> None:
                super().__init__()
                self.create_attempts = 0
                self.target_reconciliation_attempts = 0
                self.reconciled_target: TargetPlaylist | None = None

            def ensure_target_playlist(
                self, *, provider: str, name: str, visibility: str, idempotency_key: str
            ) -> TargetPlaylist:
                self.create_attempts += 1
                raise ProviderWriteError(WriteOutcome.UNKNOWN_OUTCOME, "timeout after create request")

            def reconcile_target_playlist(self, *, idempotency_key: str) -> TargetPlaylist | None:
                self.target_reconciliation_attempts += 1
                return self.reconciled_target

        digest = self.accepted_digest()
        writer = UnknownTargetWriter()
        operation = self.executor.execute(digest, writer=writer, worker_id="worker-a", now=NOW)
        self.assertEqual(operation.state, "waiting_user")
        self.assertEqual(operation.checkpoint["unknown_step"], "target")
        self.assertNotIn("target_playlist_id", operation.checkpoint)
        self.assertEqual(writer.create_attempts, 1)
        self.assertEqual(writer.added, [])

        self.operations.resume(operation.operation_id, now=NOW + timedelta(seconds=1))
        pending = self.executor.execute(digest, writer=writer, worker_id="worker-b", now=NOW + timedelta(seconds=1))
        self.assertEqual(pending.state, "waiting_user")
        self.assertEqual(writer.create_attempts, 1)
        self.assertEqual(writer.target_reconciliation_attempts, 2)

        writer.reconciled_target = writer.target
        self.operations.resume(operation.operation_id, now=NOW + timedelta(seconds=2))
        reconciled = self.executor.execute(digest, writer=writer, worker_id="worker-c", now=NOW + timedelta(seconds=2))
        self.assertEqual(reconciled.state, "succeeded")
        self.assertEqual(reconciled.checkpoint["target_playlist_id"], writer.target.provider_playlist_id)
        self.assertEqual(writer.create_attempts, 1)
        self.assertEqual(writer.added, [(f"{digest}:entry:occ-1", "target-1")])

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
        self.assertEqual(resumed.state, "waiting_user")
        self.assertEqual(resumed.checkpoint["unknown_step"], "occ-1")
        self.assertEqual(self.writer.added, [(step_key, "target-1")])
        self.assertEqual(self.writer.reconciled, [step_key, step_key])

        self.writer.reconcile_results[step_key] = True
        self.operations.resume(operation.operation_id, now=NOW + timedelta(seconds=2))
        reconciled = self.executor.execute(
            digest,
            writer=self.writer,
            worker_id="worker-c",
            now=NOW + timedelta(seconds=2),
        )
        self.assertEqual(reconciled.state, "succeeded")
        self.assertEqual(reconciled.checkpoint["confirmed_occurrences"], ["occ-1"])
        self.assertNotIn("unknown_step", reconciled.checkpoint)
        self.assertEqual(self.writer.added, [(step_key, "target-1")])

    def test_process_loss_after_entry_write_reconciles_without_duplicate(self) -> None:
        """A lost response must survive SQLite reopen and a new worker lease."""

        class SimulatedProcessLoss(BaseException):
            pass

        class CrashAfterEntry(FakeWriter):
            def add_entry(self, *, target_playlist_id: str, provider_track_id: str, idempotency_key: str) -> WriteResult:
                self.added.append((idempotency_key, provider_track_id))
                raise SimulatedProcessLoss()

        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "copy.sqlite3")
            plans = CopyPlanRepository(path)
            operations = OperationRepository(path)
            try:
                workflow = CopyWorkflowService(CopyPlanningService(), plans, operations)
                source, policy = self.snapshot()
                stored = workflow.create_plan(
                    source,
                    target_provider="youtube",
                    target_playlist_name="Rock",
                    target_visibility="private",
                    policy=policy,
                    now=NOW,
                )
                digest = workflow.accept_plan(stored.plan.digest, now=NOW).plan.digest
                queued = workflow.enqueue_accepted_plan(digest, now=NOW)
                writer = CrashAfterEntry()
                with self.assertRaises(SimulatedProcessLoss):
                    CopyExecutionService(plans, operations).execute(
                        digest, writer=writer, worker_id="worker-before-crash", now=NOW
                    )
                interrupted = operations.get(queued.operation_id)
                self.assertEqual(interrupted.state, "running")
                self.assertEqual(interrupted.checkpoint["unknown_step"], "occ-1")
            finally:
                operations.close()
                plans.close()

            plans = CopyPlanRepository(path)
            operations = OperationRepository(path)
            try:
                step_key = f"{digest}:entry:occ-1"
                writer.reconcile_results[step_key] = True
                resumed = CopyExecutionService(plans, operations).execute(
                    digest,
                    writer=writer,
                    worker_id="worker-after-restart",
                    now=NOW + timedelta(seconds=31),
                )
                self.assertEqual(resumed.state, "succeeded")
                self.assertEqual(resumed.checkpoint["confirmed_occurrences"], ["occ-1"])
                self.assertEqual(writer.reconciled, [step_key])
                self.assertEqual(writer.added, [(step_key, "target-1")])
            finally:
                operations.close()
                plans.close()

    def test_process_loss_after_target_creation_reconciles_before_any_entry(self) -> None:
        class SimulatedProcessLoss(BaseException):
            pass

        class CrashAfterTarget(FakeWriter):
            def __init__(self) -> None:
                super().__init__()
                self.create_attempts = 0
                self.reconcile_attempts = 0

            def ensure_target_playlist(
                self, *, provider: str, name: str, visibility: str, idempotency_key: str
            ) -> TargetPlaylist:
                self.create_attempts += 1
                raise SimulatedProcessLoss()

            def reconcile_target_playlist(self, *, idempotency_key: str) -> TargetPlaylist | None:
                self.reconcile_attempts += 1
                return self.target

        digest = self.accepted_digest()
        writer = CrashAfterTarget()
        with self.assertRaises(SimulatedProcessLoss):
            self.executor.execute(digest, writer=writer, worker_id="worker-before-crash", now=NOW)

        recovered = CopyExecutionService(self.plans, self.operations).execute(
            digest,
            writer=writer,
            worker_id="worker-after-restart",
            now=NOW + timedelta(seconds=31),
        )
        self.assertEqual(recovered.state, "succeeded")
        self.assertEqual(writer.create_attempts, 1)
        self.assertEqual(writer.reconcile_attempts, 1)
        self.assertEqual(writer.added, [(f"{digest}:entry:occ-1", "target-1")])

    def test_resume_skips_permanent_failure_before_reconciling_later_unknown_write(self) -> None:
        digest = self.accepted_digest(include_second_ready=True)
        first_key = f"{digest}:entry:occ-1"
        second_key = f"{digest}:entry:occ-2"
        self.writer.results[first_key] = WriteResult(WriteOutcome.PERMANENT_FAILURE, provider_code="unavailable")
        self.writer.results[second_key] = WriteResult(WriteOutcome.UNKNOWN_OUTCOME, detail="provider timeout")

        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-a", now=NOW)
        self.assertEqual(operation.state, "waiting_user")
        self.assertEqual(operation.checkpoint["unknown_step"], "occ-2")
        self.assertEqual(self.writer.added, [(first_key, "target-1"), (second_key, "target-2")])

        self.operations.resume(operation.operation_id, now=NOW + timedelta(seconds=1))
        pending = self.executor.execute(digest, writer=self.writer, worker_id="worker-b", now=NOW + timedelta(seconds=1))
        self.assertEqual(pending.state, "waiting_user")
        self.assertEqual(self.writer.added, [(first_key, "target-1"), (second_key, "target-2")])

        self.writer.reconcile_results[second_key] = True
        self.operations.resume(operation.operation_id, now=NOW + timedelta(seconds=2))
        reconciled = self.executor.execute(digest, writer=self.writer, worker_id="worker-c", now=NOW + timedelta(seconds=2))
        self.assertEqual(reconciled.state, "partial")
        self.assertEqual(reconciled.checkpoint["confirmed_occurrences"], ["occ-2"])
        self.assertEqual([issue["step"] for issue in reconciled.checkpoint["issues"]], ["occ-1"])
        self.assertEqual(self.writer.added, [(first_key, "target-1"), (second_key, "target-2")])

    def test_duplicate_confirmed_checkpoint_waits_without_provider_writes(self) -> None:
        digest = self.accepted_digest()
        self.resume_with_checkpoint(
            digest,
            {"target_playlist_id": "target-playlist-1", "confirmed_occurrences": ["occ-1", "occ-1"]},
        )

        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-b", now=NOW + timedelta(seconds=1))

        self.assertEqual(operation.state, "waiting_user")
        self.assertEqual(operation.checkpoint["failure_code"], "invalid_copy_checkpoint")
        self.assertEqual(self.writer.added, [])

    def test_conflicting_failure_checkpoint_waits_without_provider_writes(self) -> None:
        digest = self.accepted_digest()
        self.resume_with_checkpoint(
            digest,
            {
                "target_playlist_id": "target-playlist-1",
                "confirmed_occurrences": ["occ-1"],
                "issues": [{"step": "occ-1", "detail": "unavailable"}],
            },
        )

        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-b", now=NOW + timedelta(seconds=1))

        self.assertEqual(operation.state, "waiting_user")
        self.assertEqual(operation.checkpoint["failure_code"], "invalid_copy_checkpoint")
        self.assertEqual(self.writer.added, [])

    def test_out_of_order_confirmations_wait_without_provider_writes(self) -> None:
        digest = self.accepted_digest(include_second_ready=True)
        self.resume_with_checkpoint(
            digest,
            {"target_playlist_id": "target-playlist-1", "confirmed_occurrences": ["occ-2", "occ-1"]},
        )

        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-b", now=NOW + timedelta(seconds=1))

        self.assertEqual(operation.state, "waiting_user")
        self.assertEqual(operation.checkpoint["failure_code"], "invalid_copy_checkpoint")
        self.assertEqual(self.writer.added, [])

    def test_gap_in_confirmed_progress_waits_without_provider_writes(self) -> None:
        digest = self.accepted_digest(include_second_ready=True)
        self.resume_with_checkpoint(
            digest,
            {"target_playlist_id": "target-playlist-1", "confirmed_occurrences": ["occ-2"]},
        )

        operation = self.executor.execute(
            digest, writer=self.writer, worker_id="worker-b", now=NOW + timedelta(seconds=1)
        )

        self.assertEqual(operation.state, "waiting_user")
        self.assertEqual(operation.checkpoint["failure_code"], "invalid_copy_checkpoint")
        self.assertEqual(self.writer.added, [])

    def test_malformed_target_identifier_waits_without_provider_writes(self) -> None:
        digest = self.accepted_digest()
        self.resume_with_checkpoint(digest, {"target_playlist_id": ["not", "an", "id"]})

        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-b", now=NOW + timedelta(seconds=1))

        self.assertEqual(operation.state, "waiting_user")
        self.assertEqual(operation.checkpoint["failure_code"], "invalid_copy_checkpoint")
        self.assertEqual(self.writer.added, [])

    def test_retryable_write_releases_operation_until_scheduled(self) -> None:
        digest = self.accepted_digest()
        step_key = f"{digest}:entry:occ-1"
        self.writer.results[step_key] = WriteResult(WriteOutcome.RETRYABLE, provider_code="429")
        operation = self.executor.execute(digest, writer=self.writer, worker_id="worker-a", now=NOW)
        self.assertEqual(operation.state, "retry_scheduled")
        self.assertEqual(operation.next_run_at, NOW + timedelta(seconds=30))

    def test_retry_budget_turns_repeated_transient_writes_into_failure(self) -> None:
        digest = self.accepted_digest()
        step_key = f"{digest}:entry:occ-1"
        self.writer.results[step_key] = WriteResult(WriteOutcome.RETRYABLE, provider_code="temporary")
        executor = CopyExecutionService(self.plans, self.operations, retry_delay_seconds=30, max_retry_attempts=0)

        operation = executor.execute(digest, writer=self.writer, worker_id="worker-a", now=NOW)

        self.assertEqual(operation.state, "failed")
        self.assertEqual(operation.checkpoint["failure_code"], "retry_exhausted")
        self.assertEqual(operation.checkpoint["retry_attempts"], 1)

    def test_operation_runner_can_dispatch_claimed_copy_execution(self) -> None:
        digest = self.accepted_digest()
        self.workflow.enqueue_accepted_plan(digest, now=NOW)
        runner = OperationRunner(
            self.operations,
            {
                "copy_playlist": lambda operation, worker_id, now: self.executor.execute_claimed(
                    operation,
                    writer=self.writer,
                    worker_id=worker_id,
                    now=now,
                )
            },
        )
        operation = runner.run_once(worker_id="worker-a", now=NOW)
        self.assertEqual(operation.state, "succeeded")
        self.assertEqual([track for _, track in self.writer.added], ["target-1"])

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

    def test_write_boundary_redacts_credentials_in_errors_and_results(self) -> None:
        error = ProviderWriteError(
            WriteOutcome.PERMANENT_FAILURE,
            "Bearer abc123 token=secret refresh_token=refresh-value",
        )
        result = WriteResult(
            WriteOutcome.PERMANENT_FAILURE,
            provider_code="token=provider-secret",
            detail="authorization=header-value password=hunter2",
        )

        for value in (str(error), error.detail, result.detail):
            self.assertNotIn("abc123", value)
            self.assertNotIn("secret", value)
            self.assertNotIn("refresh-value", value)
            self.assertNotIn("header-value", value)
            self.assertNotIn("hunter2", value)
            self.assertNotIn("provider-secret", value)
        self.assertIn("[REDACTED]", str(error))
        self.assertIn("[REDACTED]", result.detail)
        self.assertIn("[REDACTED]", result.provider_code)


if __name__ == "__main__":
    unittest.main()
