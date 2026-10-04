"""Provider-independent durable-operation facts and lease conflict."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


class LeaseConflict(RuntimeError):
    """A caller no longer owns an eligible, live operation lease."""


@dataclass(frozen=True, slots=True)
class OperationRecord:
    operation_id: str
    operation_type: str
    state: str
    idempotency_key: str
    payload: dict[str, Any]
    checkpoint: dict[str, Any]
    worker_id: str | None
    lease_expires_at: datetime | None
    next_run_at: datetime | None
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OperationEvent:
    """Append-only audit fact for a durable operation transition."""

    sequence: int
    operation_id: str
    event_type: str
    state: str
    worker_id: str | None
    payload: dict[str, Any]
    created_at: datetime
