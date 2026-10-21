"""Serialize local publication with cancellation and operation lease changes."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import sqlite3

from symphonia.domain.operations import LeaseConflict, OperationPublicationGuard

from .sqlite_operation_codec import _utc
from .sqlite_operation_transactions import _rollback_after_error


@contextmanager
def publication_transaction(
    connection: sqlite3.Connection,
    guard: OperationPublicationGuard | None,
) -> Iterator[None]:
    """Fence a publication in the same database as its durable operation.

    BEGIN IMMEDIATE excludes competing cancellation/claim writers until the
    snapshot transaction ends. Missing operation state fails closed, including
    isolated in-memory stores; the durable wrapper requires a shared database.
    """

    try:
        connection.execute("BEGIN IMMEDIATE")
        if guard is not None:
            row = connection.execute(
                """
                SELECT state, worker_id, lease_expires_at, cancel_requested
                  FROM operations WHERE operation_id = ?
                """,
                (guard.operation_id,),
            ).fetchone()
            if (
                row is None
                or row["state"] != "running"
                or row["worker_id"] != guard.worker_id
                or row["cancel_requested"] != 0
                or row["lease_expires_at"] is None
                or row["lease_expires_at"] <= _utc(guard.clock())
            ):
                raise LeaseConflict("operation cannot publish under the supplied lease")
        yield
        connection.execute("COMMIT")
    except BaseException as error:
        _rollback_after_error(connection, error)
        raise
