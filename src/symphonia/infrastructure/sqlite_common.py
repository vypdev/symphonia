"""Shared connection policy for the dependency-free SQLite adapters."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
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


def initialize_with_cleanup(
    connection: sqlite3.Connection,
    initialize: Callable[[], None],
) -> None:
    """Close a newly opened connection if its schema initialization fails."""

    try:
        initialize()
    except BaseException as initialization_error:
        try:
            connection.close()
        except BaseException as cleanup_error:
            initialization_error.add_note(
                "SQLite connection cleanup also failed "
                f"({type(cleanup_error).__name__})"
            )
        raise


__all__ = ["connect", "dump_json", "initialize_with_cleanup", "load_json"]
