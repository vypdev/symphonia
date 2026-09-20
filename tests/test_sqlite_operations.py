from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


if __name__ == "__main__":
    unittest.main()

