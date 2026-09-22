"""Shared connection policy for the dependency-free SQLite adapters."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-standard JSON constant is not allowed: {value}")


def dump_json(value: Any) -> str:
    """Serialize adapter payloads using one strict, deterministic policy."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def load_json(value: str) -> Any:
    """Read adapter JSON without accepting NaN or Infinity extensions."""

    return json.loads(value, parse_constant=_reject_non_finite_json)


def connect(path: str) -> sqlite3.Connection:
    """Open a repository connection with the runtime safety defaults."""

    connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


__all__ = ["connect", "dump_json", "load_json"]
