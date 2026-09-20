from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import tempfile
import unittest

from symphonia.infrastructure import IdempotencyConflict, LeaseConflict, OperationRepository


UTC = timezone.utc


class OperationRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = OperationRepository()
        self.now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.repository.close()

    def test_create_is_idempotent_for_same_payload(self) -> None:
        first = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={"plan_digest": "abc"},
            now=self.now,
        )
        second = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={"plan_digest": "abc"},
            now=self.now + timedelta(seconds=1),
        )
        self.assertEqual(first.operation_id, second.operation_id)
        self.assertEqual(second.state, "queued")

    def test_same_idempotency_key_cannot_change_intent(self) -> None:
        self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={"plan_digest": "abc"},
            now=self.now,
        )
        with self.assertRaises(IdempotencyConflict):
            self.repository.create(
                operation_type="copy",
                idempotency_key="copy-1",
                payload={"plan_digest": "changed"},
                now=self.now,
            )

    def test_lease_claim_checkpoint_and_terminal_state(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={"plan_digest": "abc"},
            now=self.now,
        )
        claimed = self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        self.assertEqual(claimed.state, "running")
        self.assertEqual(claimed.worker_id, "worker-a")

        completed = self.repository.checkpoint(
            operation.operation_id,
            worker_id="worker-a",
            checkpoint={"confirmed": ["occ-1"]},
            now=self.now + timedelta(seconds=1),
            state="succeeded",
        )
        self.assertEqual(completed.state, "succeeded")
        self.assertEqual(completed.checkpoint, {"confirmed": ["occ-1"]})
        self.assertIsNone(completed.worker_id)

    def test_only_lease_owner_can_checkpoint(self) -> None:
        operation = self.repository.create(
            operation_type="import",
            idempotency_key="import-1",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        with self.assertRaises(LeaseConflict):
            self.repository.checkpoint(
                operation.operation_id,
                worker_id="worker-b",
                checkpoint={},
                now=self.now + timedelta(seconds=1),
            )

    def test_expired_lease_can_be_reclaimed_and_retry_survives(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now, lease_seconds=5)
        retry = self.repository.schedule_retry(
            operation.operation_id,
            worker_id="worker-a",
            next_run_at=self.now + timedelta(minutes=1),
            checkpoint={"last": "timeout"},
            now=self.now + timedelta(seconds=1),
        )
        self.assertEqual(retry.state, "retry_scheduled")
        self.assertEqual(retry.next_run_at, self.now + timedelta(minutes=1))
        self.assertIsNone(retry.worker_id)

        reclaimed = self.repository.claim(
            operation.operation_id,
            worker_id="worker-b",
            now=self.now + timedelta(minutes=2),
        )
        self.assertEqual(reclaimed.worker_id, "worker-b")

    def test_expired_running_lease_can_be_reclaimed(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now, lease_seconds=5)
        reclaimed = self.repository.claim(
            operation.operation_id,
            worker_id="worker-b",
            now=self.now + timedelta(seconds=6),
        )
        self.assertEqual(reclaimed.worker_id, "worker-b")

    def test_retry_cannot_be_claimed_before_its_scheduled_time(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        self.repository.schedule_retry(
            operation.operation_id,
            worker_id="worker-a",
            next_run_at=self.now + timedelta(minutes=1),
            checkpoint={"last": "rate_limited"},
            now=self.now + timedelta(seconds=1),
        )
        with self.assertRaises(LeaseConflict):
            self.repository.claim(
                operation.operation_id,
                worker_id="worker-b",
                now=self.now + timedelta(seconds=30),
            )

    def test_healthy_worker_can_renew_lease(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        claimed = self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now, lease_seconds=5)
        renewed = self.repository.renew_lease(
            operation.operation_id,
            worker_id="worker-a",
            now=self.now + timedelta(seconds=1),
            lease_seconds=60,
        )
        self.assertGreater(renewed.lease_expires_at, claimed.lease_expires_at)

    def test_waiting_user_operation_releases_lease_and_can_resume(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        waiting = self.repository.checkpoint(
            operation.operation_id,
            worker_id="worker-a",
            checkpoint={"unknown_step": "occ-1"},
            now=self.now + timedelta(seconds=1),
            state="waiting_user",
        )
        self.assertEqual(waiting.state, "waiting_user")
        self.assertIsNone(waiting.worker_id)
        resumed = self.repository.resume(operation.operation_id, now=self.now + timedelta(seconds=2))
        self.assertEqual(resumed.state, "queued")

    def test_queued_cancellation_is_terminal(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        cancelled = self.repository.cancel(operation.operation_id, now=self.now + timedelta(seconds=1))
        self.assertEqual(cancelled.state, "cancelled")
        self.assertFalse(cancelled.cancel_requested)

    def test_running_cancellation_is_acknowledged_at_checkpoint(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        claimed = self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        requested = self.repository.cancel(operation.operation_id, now=self.now + timedelta(seconds=1))
        self.assertEqual(requested.state, "running")
        self.assertTrue(requested.cancel_requested)
        completed = self.repository.checkpoint(
            claimed.operation_id,
            worker_id="worker-a",
            checkpoint={"confirmed": ["occ-1"]},
            now=self.now + timedelta(seconds=2),
            state="running",
        )
        self.assertEqual(completed.state, "cancelled")
        self.assertFalse(completed.cancel_requested)
        self.assertIsNone(completed.worker_id)

    def test_legacy_store_is_migrated_forward_without_losing_operations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/legacy.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE operations (
                    operation_id TEXT PRIMARY KEY,
                    operation_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    worker_id TEXT,
                    lease_expires_at TEXT,
                    next_run_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                PRAGMA user_version = 1;
                """
            )
            connection.execute(
                """
                INSERT INTO operations (
                    operation_id, operation_type, state, idempotency_key,
                    payload_json, checkpoint_json, created_at, updated_at
                ) VALUES ('legacy-1', 'copy', 'queued', 'legacy-key', '{}', '{}', ?, ?)
                """,
                (self.now.isoformat(), self.now.isoformat()),
            )
            connection.commit()
            connection.close()

            repository = OperationRepository(path)
            try:
                record = repository.get("legacy-1")
                self.assertFalse(record.cancel_requested)
                self.assertEqual(
                    repository._connection.execute("PRAGMA user_version").fetchone()[0],
                    OperationRepository.SCHEMA_VERSION,
                )
            finally:
                repository.close()


if __name__ == "__main__":
    unittest.main()
