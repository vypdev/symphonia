from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.identity import (
    AssessmentClass,
    Evidence,
    EvidenceKind,
    ManualDecision,
    ManualDecisionAction,
    normalize_isrc,
    normalize_recording_metadata,
    normalize_text,
    version_tokens,
)
from symphonia.infrastructure import ResolutionDecisionRepository


class IdentityResolutionTests(unittest.TestCase):
    def test_normalization_is_unicode_safe_and_lossless(self) -> None:
        metadata = normalize_recording_metadata(
            title="Beyoncé — Halo (Live Edit)",
            artists=("Beyoncé", "  Jay-Z  "),
            isrc="us-r1a-99-01234",
        )

        self.assertEqual(metadata.original_title, "Beyoncé — Halo (Live Edit)")
        self.assertEqual(metadata.normalized_title, "beyoncé halo live edit")
        self.assertEqual(metadata.original_artists, ("Beyoncé", "  Jay-Z  "))
        self.assertEqual(metadata.normalized_artists, ("beyoncé", "jay z"))
        self.assertEqual(metadata.version_tokens, ("live", "edit"))
        self.assertEqual(metadata.normalized_isrc, "USR1A9901234")

    def test_isrc_validation_never_turns_malformed_input_into_identity(self) -> None:
        self.assertEqual(normalize_isrc("US-R1A-99-01234"), "USR1A9901234")
        self.assertIsNone(normalize_isrc("not-an-isrc"))
        self.assertEqual(normalize_text("  Café\u00a0del\u00a0Mar  "), "café del mar")
        self.assertEqual(version_tokens("Song (Acoustic Remix)"), ("acoustic", "remix"))

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
