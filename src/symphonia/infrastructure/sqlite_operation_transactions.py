"""Shared connection locking and interruption-safe transaction rollback."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
import sqlite3
from typing import Any, Concatenate, ParamSpec, TypeVar


def _rollback_after_error(connection: sqlite3.Connection, error: BaseException) -> None:
    """Release an interrupted transaction without hiding its primary failure."""

    if not connection.in_transaction:
        return
    try:
        connection.execute("ROLLBACK")
    except BaseException as rollback_error:
        error.add_note(
            "SQLite transaction rollback also failed "
            f"({type(rollback_error).__name__})"
        )


_RepositoryArgs = ParamSpec("_RepositoryArgs")
_RepositoryResult = TypeVar("_RepositoryResult")


def _serialize_repository_access(
    method: Callable[Concatenate[Any, _RepositoryArgs], _RepositoryResult],
) -> Callable[Concatenate[Any, _RepositoryArgs], _RepositoryResult]:
    """Keep each use of a shared SQLite connection within one local critical section."""

    @wraps(method)
    def wrapped(
        self: Any,
        *args: _RepositoryArgs.args,
        **kwargs: _RepositoryArgs.kwargs,
    ) -> _RepositoryResult:
        with self._connection_lock:
            return method(self, *args, **kwargs)

    return wrapped
