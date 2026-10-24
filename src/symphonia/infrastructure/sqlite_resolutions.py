"""Append-only SQLite storage for manual identity decisions."""

from __future__ import annotations

from dataclasses import replace
import sqlite3
import uuid
from typing import Any

from symphonia.identity.models import ManualDecision, ManualDecisionAction

from .sqlite_common import connect, dump_json, initialize_with_cleanup, load_json


class ResolutionDecisionRepository:
    """Preserve every decision; latest state never erases prior authorship."""

    def __init__(self, path: str = ":memory:") -> None:
        self._connection = connect(path)
        initialize_with_cleanup(self._connection, self._migrate)

    def close(self) -> None:
        self._connection.close()

    def healthcheck(self) -> bool:
        """Return whether schema and decision payloads are readable."""

        try:
            integrity = self._connection.execute("PRAGMA integrity_check(1)").fetchone()
            if integrity is None or integrity[0] != "ok":
                return False
            for row in self._connection.execute("SELECT payload_json FROM resolution_decisions").fetchall():
                payload = load_json(row["payload_json"])
                if not isinstance(payload, dict):
                    return False
        except (sqlite3.Error, TypeError, ValueError):
            return False
        return True

    def _migrate(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS resolution_decisions (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id TEXT NOT NULL UNIQUE,
                provider_track_key TEXT NOT NULL,
                candidate_recording_id TEXT,
                action TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS resolution_decisions_lookup_idx
                ON resolution_decisions (provider_track_key, candidate_recording_id, sequence);
            """
        )

    def record(self, decision: ManualDecision) -> ManualDecision:
        decision_id = decision.decision_id or str(uuid.uuid4())
        persisted = replace(decision, decision_id=decision_id)
        payload = dump_json(
            {
                "provider_track_key": persisted.provider_track_key,
                "candidate_recording_id": persisted.candidate_recording_id,
                "action": persisted.action.value,
                "actor_id": persisted.actor_id,
                "reason": persisted.reason,
                "created_at": persisted.created_at,
            },
        )
        self._connection.execute(
            """
            INSERT INTO resolution_decisions (
                decision_id, provider_track_key, candidate_recording_id, action,
                actor_id, reason, created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                persisted.decision_id,
                persisted.provider_track_key,
                persisted.candidate_recording_id,
                persisted.action.value,
                persisted.actor_id,
                persisted.reason,
                persisted.created_at,
                payload,
            ),
        )
        return persisted

    def latest(self, provider_track_key: str, candidate_recording_id: str | None) -> ManualDecision | None:
        row = self._connection.execute(
            """
            SELECT * FROM resolution_decisions
             WHERE provider_track_key = ?
               AND candidate_recording_id IS ?
             ORDER BY sequence DESC LIMIT 1
            """,
            (provider_track_key, candidate_recording_id),
        ).fetchone()
        if row is None:
            return None
        return ManualDecision(
            provider_track_key=row["provider_track_key"],
            candidate_recording_id=row["candidate_recording_id"],
            action=ManualDecisionAction(row["action"]),
            actor_id=row["actor_id"],
            reason=row["reason"],
            created_at=row["created_at"],
            decision_id=row["decision_id"],
        )

    def count(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM resolution_decisions").fetchone()[0])

    def summary(self) -> dict[str, Any]:
        """Return decision counts without track, candidate, actor, or reason data."""

        rows = self._connection.execute(
            """
            SELECT action, COUNT(*) AS count
              FROM resolution_decisions
             GROUP BY action
             ORDER BY action
            """
        ).fetchall()
        by_action = {str(row["action"]): int(row["count"]) for row in rows}
        return {"total": sum(by_action.values()), "by_action": by_action}
