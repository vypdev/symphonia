from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.identity import (
    AssessmentClass,
    Evidence,
    EvidenceKind,
    ManualDecision,
    ManualDecisionAction,
)
from symphonia.infrastructure import ResolutionDecisionRepository


class IdentityResolutionTests(unittest.TestCase):
    def test_unmatched_assessment_has_no_candidate(self) -> None:
        from symphonia.identity.models import CandidateAssessment

        assessment = CandidateAssessment(
            provider_track_key="spotify:connection-1:track-1",
            candidate_recording_id=None,
            classification=AssessmentClass.UNMATCHED,
            evidence=(),
            resolver_version="rules-1",
        )
        self.assertEqual(assessment.classification, AssessmentClass.UNMATCHED)

    def test_matched_assessment_requires_explainable_evidence(self) -> None:
        from symphonia.identity.models import CandidateAssessment

        with self.assertRaises(ValueError):
            CandidateAssessment(
                provider_track_key="spotify:connection-1:track-1",
                candidate_recording_id="recording-1",
                classification=AssessmentClass.HIGH_CONFIDENCE,
                evidence=(),
                resolver_version="rules-1",
            )

        assessment = CandidateAssessment(
            provider_track_key="spotify:connection-1:track-1",
            candidate_recording_id="recording-1",
            classification=AssessmentClass.HIGH_CONFIDENCE,
            evidence=(Evidence(EvidenceKind.ISRC, "ISRC matches", True, "provider metadata"),),
            resolver_version="rules-1",
        )
        self.assertEqual(assessment.evidence[0].kind, EvidenceKind.ISRC)

    def test_manual_decisions_are_append_only_and_latest_is_explicit(self) -> None:
        repository = ResolutionDecisionRepository()
        try:
            first = repository.record(
                ManualDecision(
                    provider_track_key="spotify:connection-1:track-1",
                    candidate_recording_id="recording-1",
                    action=ManualDecisionAction.REJECT,
                    actor_id="local-user",
                    reason="Live version, not the studio recording",
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            latest = repository.latest("spotify:connection-1:track-1", "recording-1")
            self.assertEqual(latest.decision_id, first.decision_id)
            self.assertEqual(latest.action, ManualDecisionAction.REJECT)

            repository.record(
                ManualDecision(
                    provider_track_key="spotify:connection-1:track-1",
                    candidate_recording_id="recording-1",
                    action=ManualDecisionAction.ACCEPT,
                    actor_id="local-user",
                    reason="Verified the exact recording",
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            latest = repository.latest("spotify:connection-1:track-1", "recording-1")
            self.assertEqual(latest.action, ManualDecisionAction.ACCEPT)
            self.assertEqual(repository.count(), 2)
        finally:
            repository.close()


if __name__ == "__main__":
    unittest.main()

