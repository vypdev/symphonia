"""Shared transaction resources used by cohesive operation-store adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import sqlite3
from typing import Any, Protocol

from symphonia.domain.operations import OperationRecord


class EventAppender(Protocol):
    def __call__(
        self, *, operation_id: str, event_type: str, state: str,
        worker_id: str | None, payload: dict[str, Any], created_at: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class OperationContext:
    connection: sqlite3.Connection
    get: Callable[[str], OperationRecord]
    append_event: EventAppender
