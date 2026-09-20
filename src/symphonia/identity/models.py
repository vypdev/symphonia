"""Provider-independent identity-resolution values.

This module deliberately models evidence and decisions, not a final matching
algorithm. Thresholds and candidate retrieval remain provider/policy work that
must be accepted separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ResolutionState(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"
    DEFERRED = "deferred"
    INVALID = "invalid"


class AssessmentClass(str, Enum):
    EXACT = "exact"
    HIGH_CONFIDENCE = "high_confidence"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"


class EvidenceKind(str, Enum):
    ISRC = "isrc"
    TITLE = "title"
    ARTIST = "artist"
    DURATION = "duration"
    VERSION = "version"
    RELEASE = "release"
    PROVIDER_METADATA = "provider_metadata"


class ManualDecisionAction(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    DISTINCT = "distinct"
    DEFER = "defer"
    REVOKE = "revoke"


@dataclass(frozen=True, slots=True)
class Evidence:
    kind: EvidenceKind
    summary: str
    supports: bool
    source: str

    def __post_init__(self) -> None:
        if not self.summary.strip() or not self.source.strip():
            raise ValueError("evidence summary and source must not be empty")


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    provider_track_key: str
    candidate_recording_id: str | None
    classification: AssessmentClass
    evidence: tuple[Evidence, ...]
    resolver_version: str

    def __post_init__(self) -> None:
        if not self.provider_track_key.strip() or not self.resolver_version.strip():
            raise ValueError("provider_track_key and resolver_version must not be empty")
        if self.classification is AssessmentClass.UNMATCHED:
            if self.candidate_recording_id is not None:
                raise ValueError("unmatched assessments cannot name a candidate")
        elif not self.candidate_recording_id or not self.evidence:
            raise ValueError("matched assessments require a candidate and evidence")


@dataclass(frozen=True, slots=True)
class ManualDecision:
    provider_track_key: str
    candidate_recording_id: str | None
    action: ManualDecisionAction
    actor_id: str
    reason: str
    created_at: str
    decision_id: str | None = None

    def __post_init__(self) -> None:
        if not self.provider_track_key.strip() or not self.actor_id.strip() or not self.reason.strip():
            raise ValueError("manual decisions require track, actor, and reason")
        if self.action in {ManualDecisionAction.ACCEPT, ManualDecisionAction.REJECT} and not self.candidate_recording_id:
            raise ValueError("accept/reject decisions require a candidate recording")

