"""Durable storage for immutable copy plans and their acceptance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any

from symphonia.domain.models import (
    CopyPlan,
    CopyPlanEntry,
    CopyPolicy,
    EntryClassification,
    PlanAcceptanceError,
)


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class CopyPlanNotFound(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class StoredCopyPlan:
    plan: CopyPlan
    accepted_at: datetime | None


class CopyPlanRepository:
    """A small SQLite adapter that never mutates a plan after creation."""

    def __init__(self, path: str = ":memory:") -> None:
        self._connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self._connection.close()

    def _migrate(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS copy_plans (
                digest TEXT PRIMARY KEY,
                plan_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                accepted_at TEXT
            );
            """
        )

    def save(self, plan: CopyPlan, *, now: datetime) -> StoredCopyPlan:
        payload = _serialize(plan)
        plan_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self._connection.execute(
            "INSERT OR IGNORE INTO copy_plans (digest, plan_json, created_at) VALUES (?, ?, ?)",
            (plan.digest, plan_json, _utc(now)),
        )
        stored = self.get(plan.digest)
        if stored.plan != plan:
            raise ValueError("digest collision or attempted mutation of an existing plan")
        return stored

    def get(self, digest: str) -> StoredCopyPlan:
        row = self._connection.execute(
            "SELECT * FROM copy_plans WHERE digest = ?", (digest,)
        ).fetchone()
        if row is None:
            raise CopyPlanNotFound(digest)
        return StoredCopyPlan(
            plan=_deserialize(json.loads(row["plan_json"])),
            accepted_at=None if row["accepted_at"] is None else _parse_utc(row["accepted_at"]),
        )

    def accept(self, digest: str, *, expected_digest: str, now: datetime) -> StoredCopyPlan:
        stored = self.get(digest)
        if stored.plan.digest != expected_digest:
            raise PlanAcceptanceError("accepted digest does not match the stored plan")
        # Reuse domain validation so strict blocked plans and digest changes
        # cannot be bypassed by persistence code.
        stored.plan.accept(expected_digest)
        self._connection.execute(
            "UPDATE copy_plans SET accepted_at = COALESCE(accepted_at, ?) WHERE digest = ?",
            (_utc(now), digest),
        )
        return self.get(digest)


def _serialize(plan: CopyPlan) -> dict[str, Any]:
    return {
        "source_snapshot_id": plan.source_snapshot_id,
        "source_provider": plan.source_provider,
        "source_playlist_id": plan.source_playlist_id,
        "source_namespace": plan.source_namespace,
        "target_provider": plan.target_provider,
        "target_connection_id": plan.target_connection_id,
        "target_capabilities": list(plan.target_capabilities),
        "target_capability_evidence_version": plan.target_capability_evidence_version,
        "target_playlist_name": plan.target_playlist_name,
        "target_visibility": plan.target_visibility,
        "policy": plan.policy.value,
        "entries": [
            {
                "occurrence_id": entry.occurrence_id,
                "position": entry.position,
                "classification": entry.classification.value,
                "disposition": entry.disposition,
                "target_track_id": entry.target_track_id,
                "reason": entry.reason,
                "evidence": list(entry.evidence),
                "source_provider_track_object_type": entry.source_provider_track_object_type,
            }
            for entry in plan.entries
        ],
        "digest": plan.digest,
    }


def _deserialize(payload: dict[str, Any]) -> CopyPlan:
    return CopyPlan(
        source_snapshot_id=payload["source_snapshot_id"],
        source_provider=payload["source_provider"],
        source_playlist_id=payload["source_playlist_id"],
        target_provider=payload["target_provider"],
        target_playlist_name=payload["target_playlist_name"],
        target_visibility=payload["target_visibility"],
        policy=CopyPolicy(payload["policy"]),
        entries=tuple(
            CopyPlanEntry(
                occurrence_id=entry["occurrence_id"],
                position=entry["position"],
                classification=EntryClassification(entry["classification"]),
                disposition=entry["disposition"],
                target_track_id=entry["target_track_id"],
                reason=entry["reason"],
                evidence=tuple(entry["evidence"]),
                source_provider_track_object_type=entry.get("source_provider_track_object_type", "track"),
            )
            for entry in payload["entries"]
        ),
        digest=payload["digest"],
        source_namespace=payload.get("source_namespace", "default"),
        target_connection_id=payload.get("target_connection_id", "default"),
        target_capabilities=tuple(payload.get("target_capabilities", ())),
        target_capability_evidence_version=payload.get("target_capability_evidence_version"),
    )
