"""Pure domain values used by the first copy-planning slice.

No provider SDK, HTTP framework, database driver, or Home Assistant package is
allowed in this module. The planner consumes normalized provider-independent
values and emits an immutable plan that can be persisted by an outer layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable


class EntryClassification(str, Enum):
    """The six source-entry classifications required by the product model."""

    READY = "ready"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


class CopyPolicy(str, Enum):
    """How a copy plan treats entries that are not ready to write."""

    STRICT = "strict"
    BEST_EFFORT = "best_effort"


class PlanAcceptanceError(ValueError):
    """Raised when an immutable plan cannot be accepted safely."""


@dataclass(frozen=True, slots=True)
class SourcePlaylistEntry:
    """One occurrence in a captured source playlist snapshot.

    ``position`` is occurrence-specific: two equal provider track IDs at two
    positions remain two separate entries. ``target_track_id`` is supplied by
    a normalized resolution/projection step and is intentionally opaque.
    """

    occurrence_id: str
    position: int
    provider_track_id: str
    classification: EntryClassification
    target_track_id: str | None = None
    evidence: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.occurrence_id.strip():
            raise ValueError("occurrence_id must not be empty")
        if self.position < 0:
            raise ValueError("position must be non-negative")
        if not self.provider_track_id.strip():
            raise ValueError("provider_track_id must not be empty")
        if self.classification is EntryClassification.READY and not self.target_track_id:
            raise ValueError("ready entries require a target_track_id")
        if self.target_track_id is not None and not self.target_track_id.strip():
            raise ValueError("target_track_id must not be blank")


@dataclass(frozen=True, slots=True)
class PlaylistSnapshot:
    """Immutable, ordered observation used as the sole planning input."""

    snapshot_id: str
    source_provider: str
    source_playlist_id: str
    entries: tuple[SourcePlaylistEntry, ...]

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.snapshot_id, "snapshot_id"),
            (self.source_provider, "source_provider"),
            (self.source_playlist_id, "source_playlist_id"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")

        positions = [entry.position for entry in self.entries]
        occurrence_ids = [entry.occurrence_id for entry in self.entries]
        if positions != sorted(positions):
            raise ValueError("snapshot entries must be ordered by position")
        if len(positions) != len(set(positions)):
            raise ValueError("snapshot positions must be unique")
        if len(occurrence_ids) != len(set(occurrence_ids)):
            raise ValueError("snapshot occurrence IDs must be unique")


@dataclass(frozen=True, slots=True)
class CopyPlanEntry:
    """Planned disposition for one source occurrence."""

    occurrence_id: str
    position: int
    classification: EntryClassification
    disposition: str
    target_track_id: str | None
    reason: str | None
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.disposition not in {"write", "blocked", "omit"}:
            raise ValueError("disposition must be write, blocked, or omit")
        if self.disposition == "write" and not self.target_track_id:
            raise ValueError("write entries require a target_track_id")


@dataclass(frozen=True, slots=True)
class CopyPlan:
    """Immutable dry-run output with a tamper-evident digest."""

    source_snapshot_id: str
    source_provider: str
    source_playlist_id: str
    target_provider: str
    target_playlist_name: str
    target_visibility: str
    policy: CopyPolicy
    entries: tuple[CopyPlanEntry, ...]
    digest: str

    @property
    def blocked(self) -> bool:
        return any(entry.disposition == "blocked" for entry in self.entries)

    @property
    def writable_entries(self) -> tuple[CopyPlanEntry, ...]:
        return tuple(entry for entry in self.entries if entry.disposition == "write")

    @property
    def omitted_entries(self) -> tuple[CopyPlanEntry, ...]:
        return tuple(entry for entry in self.entries if entry.disposition == "omit")

    def accept(self, expected_digest: str) -> "AcceptedCopyPlan":
        """Bind execution to this exact plan digest."""

        if expected_digest != self.digest:
            raise PlanAcceptanceError("plan digest does not match the requested acceptance")
        if self.blocked:
            raise PlanAcceptanceError("plan contains blocked entries")
        return AcceptedCopyPlan(plan=self, accepted_digest=self.digest)


@dataclass(frozen=True, slots=True)
class AcceptedCopyPlan:
    """Accepted immutable plan; execution may only use this value."""

    plan: CopyPlan
    accepted_digest: str


def build_copy_plan(
    snapshot: PlaylistSnapshot,
    *,
    target_provider: str,
    target_playlist_name: str,
    target_visibility: str = "private",
    policy: CopyPolicy = CopyPolicy.STRICT,
) -> CopyPlan:
    """Build a non-mutating, deterministic copy plan.

    Strict plans block every non-ready occurrence. Best-effort plans explicitly
    omit those occurrences while retaining their classification and reason.
    No provider write can be performed by this function.
    """

    if not target_provider.strip():
        raise ValueError("target_provider must not be empty")
    if not target_playlist_name.strip():
        raise ValueError("target_playlist_name must not be empty")
    if not target_visibility.strip():
        raise ValueError("target_visibility must not be empty")

    plan_entries: list[CopyPlanEntry] = []
    for source in snapshot.entries:
        ready = source.classification is EntryClassification.READY
        disposition = "write" if ready else ("blocked" if policy is CopyPolicy.STRICT else "omit")
        reason = source.reason
        if not ready and reason is None:
            reason = f"source entry is {source.classification.value}"
        plan_entries.append(
            CopyPlanEntry(
                occurrence_id=source.occurrence_id,
                position=source.position,
                classification=source.classification,
                disposition=disposition,
                target_track_id=source.target_track_id if ready else None,
                reason=reason,
                evidence=source.evidence,
            )
        )

    canonical = {
        "source_snapshot_id": snapshot.snapshot_id,
        "source_provider": snapshot.source_provider,
        "source_playlist_id": snapshot.source_playlist_id,
        "target_provider": target_provider,
        "target_playlist_name": target_playlist_name,
        "target_visibility": target_visibility,
        "policy": policy.value,
        "entries": [
            {
                "occurrence_id": entry.occurrence_id,
                "position": entry.position,
                "classification": entry.classification.value,
                "disposition": entry.disposition,
                "target_track_id": entry.target_track_id,
                "reason": entry.reason,
                "evidence": list(entry.evidence),
            }
            for entry in plan_entries
        ],
    }
    serialized = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return CopyPlan(
        source_snapshot_id=snapshot.snapshot_id,
        source_provider=snapshot.source_provider,
        source_playlist_id=snapshot.source_playlist_id,
        target_provider=target_provider,
        target_playlist_name=target_playlist_name,
        target_visibility=target_visibility,
        policy=policy,
        entries=tuple(plan_entries),
        digest=digest,
    )


def source_entries(entries: Iterable[SourcePlaylistEntry]) -> tuple[SourcePlaylistEntry, ...]:
    """Convenience helper for callers constructing a snapshot."""

    return tuple(entries)

