from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

    def test_polling_survives_lost_ownership_and_handles_later_work(self) -> None:
        later = self.repository.create(operation_type="fixture", idempotency_key="worker-later", payload={}, now=NOW)
        stop_event = threading.Event()
        attempts = []
        clock_now = [NOW]

        def handler(operation, worker_id, now):
            attempts.append(operation.operation_id)
            if len(attempts) == 1:
                clock_now[0] = now + timedelta(seconds=31)
                self.repository.claim(operation.operation_id, worker_id="other-worker", now=clock_now[0])
                return self.repository.checkpoint(operation.operation_id, worker_id=worker_id,
                                                  checkpoint={}, now=clock_now[0], state="succeeded")
            result = self.repository.checkpoint(operation.operation_id, worker_id=worker_id,
                                                checkpoint={}, now=now, state="succeeded")
            stop_event.set()
            return result

        class ObserveWait(threading.Event):
            def wait(self, timeout=None):
                waits.append(timeout)
                return False

            def is_set(self):
                return stop_event.is_set()

        waits = []
        worker = OperationWorker(OperationRunner(self.repository, {"fixture": handler}), worker_id="worker",
                                 clock=lambda: clock_now[0], poll_interval_seconds=0.25)
        worker.run_forever(ObserveWait())
        self.assertEqual(set(attempts), {self.operation.operation_id, later.operation_id})
        self.assertEqual(len(attempts), 2)
        self.assertEqual(waits, [0.25])
        self.assertEqual(self.repository.get(attempts[0]).worker_id, "other-worker")
        self.assertEqual(self.repository.get(attempts[0]).state, "running")
        self.assertEqual(self.repository.get(attempts[1]).state, "succeeded")

    def test_worker_rejects_invalid_identity_and_timing_values(self) -> None:
        runner = OperationRunner(self.repository, {})
        invalid_values = (
            {"worker_id": None},
            {"worker_id": "worker", "poll_interval_seconds": True},
            {"worker_id": "worker", "poll_interval_seconds": float("nan")},
            {"worker_id": "worker", "lease_seconds": True},
            {"worker_id": "worker", "lease_seconds": 0.5},
        )
        for values in invalid_values:
            with self.subTest(values=values), self.assertRaises(ValueError):
                OperationWorker(runner, **values)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
