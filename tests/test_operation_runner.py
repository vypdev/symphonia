from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.application import OperationRunner
from symphonia.infrastructure import OperationRepository


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


class OperationRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = OperationRepository()

    def tearDown(self) -> None:
        self.repository.close()

    def test_runner_dispatches_only_durable_eligible_work(self) -> None:
        operation = self.repository.create(
            operation_type="fixture",
            idempotency_key="fixture-1",
            payload={},
            now=NOW,
        )
        calls = []

        def handler(claimed, worker_id, now):
            calls.append((claimed.operation_id, worker_id))
            return self.repository.checkpoint(
                claimed.operation_id,
                worker_id=worker_id,
                checkpoint={"done": True},
                now=now,
                state="succeeded",
            )

        runner = OperationRunner(self.repository, {"fixture": handler})
        completed = runner.run_once(worker_id="worker-a", now=NOW)
        self.assertEqual(completed.state, "succeeded")
        self.assertEqual(calls, [(operation.operation_id, "worker-a")])
        self.assertIsNone(runner.run_once(worker_id="worker-a", now=NOW))

    def test_missing_handler_fails_before_external_work(self) -> None:
        operation = self.repository.create(
            operation_type="unwired",
            idempotency_key="unwired-1",
            payload={},
            now=NOW,
        )
        result = OperationRunner(self.repository, {}).run_once(worker_id="worker-a", now=NOW)
        self.assertEqual(result.operation_id, operation.operation_id)
        self.assertEqual(result.state, "failed")
        self.assertEqual(result.checkpoint["failure_code"], "handler_not_registered")
        self.assertEqual(
            [event.event_type for event in self.repository.events(operation.operation_id)],
            ["created", "claimed", "checkpointed"],
        )


if __name__ == "__main__":
    unittest.main()
