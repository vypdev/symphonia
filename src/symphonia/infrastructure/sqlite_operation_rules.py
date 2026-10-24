"""Store-level operation identifiers and recovery preconditions."""

from __future__ import annotations

from typing import Any


class OperationNotFound(LookupError):
    pass


class IdempotencyConflict(ValueError):
    pass


def _require_positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _checkpoint_requires_reconciliation(checkpoint: dict[str, Any]) -> bool:
    return (
        checkpoint.get("unknown_step") is not None
        or checkpoint.get("reconciliation_required") is True
    )
