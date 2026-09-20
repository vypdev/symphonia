"""Small durable-operation dispatcher for the single-process runtime profile."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from symphonia.infrastructure.sqlite_operations import OperationRecord, OperationRepository


OperationHandler = Callable[[OperationRecord, str, datetime], OperationRecord]


@dataclass(frozen=True, slots=True)
class OperationRunner:
    operations: OperationRepository
    handlers: Mapping[str, OperationHandler]

    def run_once(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 30,
        operation_type: str | None = None,
    ) -> OperationRecord | None:
        operation = self.operations.claim_next(
            worker_id=worker_id,
            now=now,
            lease_seconds=lease_seconds,
            operation_type=operation_type,
        )
        if operation is None:
            return None
        handler = self.handlers.get(operation.operation_type)
        if handler is None:
            return self.operations.checkpoint(
                operation.operation_id,
                worker_id=worker_id,
                checkpoint={**operation.checkpoint, "failure_code": "handler_not_registered"},
                now=now,
                state="failed",
            )
        return handler(operation, worker_id, now)

