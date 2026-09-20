"""Append-only SQLite storage for manual identity decisions."""

from __future__ import annotations

from dataclasses import replace
import json
import sqlite3
import uuid

from symphonia.identity.models import ManualDecision, ManualDecisionAction


class ResolutionDecisionRepository:
    """Preserve every decision; latest state never erases prior authorship."""

    def __init__(self, path: str = ":memory:") -> None:
        self._connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self._connection.close()

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
        payload = json.dumps(
            {
                "provider_track_key": persisted.provider_track_key,
                "candidate_recording_id": persisted.candidate_recording_id,
                "action": persisted.action.value,
                "actor_id": persisted.actor_id,
                "reason": persisted.reason,
                "created_at": persisted.created_at,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
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

