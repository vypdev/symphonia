from __future__ import annotations

from datetime import datetime, timezone
import threading
import unittest

from symphonia.application import OperationRunner, OperationWorker
from symphonia.infrastructure import OperationRepository


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


class OperationWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = OperationRepository()
        self.operation = self.repository.create(
            operation_type="fixture",
            idempotency_key="worker-1",
            payload={},
            now=NOW,
        )

    def tearDown(self) -> None:
        self.repository.close()

    def test_run_once_uses_injected_clock_and_worker_identity(self) -> None:
        seen: list[tuple[str, datetime]] = []

        def handler(operation, worker_id, now):
            seen.append((worker_id, now))
            return self.repository.checkpoint(
                operation.operation_id,
                worker_id=worker_id,
                checkpoint={"handled": True},
                now=now,
                state="succeeded",
            )

        runner = OperationRunner(self.repository, {"fixture": handler})
        worker = OperationWorker(runner, worker_id="app-worker-1", clock=lambda: NOW)

        result = worker.run_once()

        self.assertEqual(result.operation_id, self.operation.operation_id)
        self.assertEqual(result.state, "succeeded")
        self.assertEqual(seen, [("app-worker-1", NOW)])
        self.assertIsNone(worker.run_once())

    def test_run_forever_waits_interruptibly_when_queue_is_empty(self) -> None:
        runner = OperationRunner(self.repository, {})
        worker = OperationWorker(runner, worker_id="app-worker-1", clock=lambda: NOW, poll_interval_seconds=0.25)
        class StopAfterWait(threading.Event):
            def wait(self, timeout=None):
                self.set()
                return True

        stop_event = StopAfterWait()

        worker.run_forever(stop_event)

        self.assertTrue(stop_event.is_set())


if __name__ == "__main__":
    unittest.main()
