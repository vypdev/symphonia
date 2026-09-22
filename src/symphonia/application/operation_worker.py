"""Cooperative single-process worker for durable operations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import math
import threading

from symphonia.infrastructure.sqlite_operations import OperationRecord

from .operation_runner import OperationRunner


Clock = Callable[[], datetime]


class OperationWorker:
    """Poll an :class:`OperationRunner` without making memory authoritative.

    The worker is deliberately small and single-process. Every iteration
    claims through the durable repository, so a stop or crash only delays work
    until the lease expires; it cannot turn an in-memory queue into the source
    of truth.
    """

    def __init__(
        self,
        runner: OperationRunner,
        *,
        worker_id: str,
        clock: Clock | None = None,
        poll_interval_seconds: float = 1.0,
        lease_seconds: int = 30,
    ) -> None:
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if (
            isinstance(poll_interval_seconds, bool)
            or not isinstance(poll_interval_seconds, (int, float))
            or not math.isfinite(poll_interval_seconds)
            or poll_interval_seconds <= 0
        ):
            raise ValueError("poll_interval_seconds must be positive")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self._runner = runner
        self._worker_id = worker_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._poll_interval_seconds = poll_interval_seconds
        self._lease_seconds = lease_seconds

    @property
    def worker_id(self) -> str:
        return self._worker_id

    def run_once(self, *, operation_type: str | None = None) -> OperationRecord | None:
        """Claim and dispatch one eligible operation, if one exists."""

        return self._runner.run_once(
            worker_id=self._worker_id,
            now=self._clock(),
            lease_seconds=self._lease_seconds,
            operation_type=operation_type,
        )

    def run_forever(self, stop_event: threading.Event) -> None:
        """Poll until requested to stop; waiting remains interruptible."""

        while not stop_event.is_set():
            operation = self.run_once()
            if operation is None:
                stop_event.wait(self._poll_interval_seconds)


__all__ = ["OperationWorker"]
