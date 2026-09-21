"""Shared connection policy for the dependency-free SQLite adapters."""

from __future__ import annotations

import sqlite3


def connect(path: str) -> sqlite3.Connection:
    """Open a repository connection with the runtime safety defaults."""

    connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


__all__ = ["connect"]
