from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.domain import CopyPolicy, EntryClassification, PlanAcceptanceError, PlaylistSnapshot, SourcePlaylistEntry
from symphonia.domain.models import build_copy_plan
from symphonia.infrastructure import CopyPlanRepository


class CopyPlanRepositoryTests(unittest.TestCase):
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)

    def setUp(self) -> None:
        self.repository = CopyPlanRepository()

    def tearDown(self) -> None:
        self.repository.close()

    def ready_plan(self):
        snapshot = PlaylistSnapshot(
            snapshot_id="snapshot-1",
            source_provider="spotify",
            source_playlist_id="playlist-1",
            entries=(SourcePlaylistEntry("occ-1", 0, "sp-1", EntryClassification.READY, "yt-1"),),
        )
        return build_copy_plan(
            snapshot,
            target_provider="youtube",
            target_playlist_name="Rock",
            policy=CopyPolicy.STRICT,
        )

    def test_save_and_reload_preserves_immutable_plan_and_digest(self) -> None:
        plan = self.ready_plan()
        self.repository.save(plan, now=self.now)
        stored = self.repository.get(plan.digest)
        self.assertEqual(stored.plan, plan)
        self.assertIsNone(stored.accepted_at)

    def test_plan_json_rejects_non_standard_numbers_on_read(self) -> None:
        plan = self.ready_plan()
        self.repository.save(plan, now=self.now)
        self.repository._connection.execute(  # type: ignore[attr-defined]
            "UPDATE copy_plans SET plan_json = ? WHERE digest = ?",
            ('{"source_snapshot_id": NaN}', plan.digest),
        )

        self.assertFalse(self.repository.healthcheck())
        with self.assertRaises(ValueError):
            self.repository.get(plan.digest)

    def test_plan_json_rejects_content_tampering_with_an_unchanged_digest(self) -> None:
        plan = self.ready_plan()
        self.repository.save(plan, now=self.now)
        raw = self.repository._connection.execute(  # type: ignore[attr-defined]
            "SELECT plan_json FROM copy_plans WHERE digest = ?",
            (plan.digest,),
        ).fetchone()["plan_json"]
        tampered = raw.replace('"target_playlist_name":"Rock"', '"target_playlist_name":"Tampered"')
        self.assertNotEqual(raw, tampered)
        self.repository._connection.execute(  # type: ignore[attr-defined]
            "UPDATE copy_plans SET plan_json = ? WHERE digest = ?",
            (tampered, plan.digest),
        )

        self.assertFalse(self.repository.healthcheck())
        with self.assertRaises(ValueError):
            self.repository.get(plan.digest)

    def test_acceptance_is_durable_and_idempotent(self) -> None:
        plan = self.ready_plan()
        self.repository.save(plan, now=self.now)
        first = self.repository.accept(plan.digest, expected_digest=plan.digest, now=self.now)
        second = self.repository.accept(
            plan.digest,
            expected_digest=plan.digest,
            now=self.now.replace(hour=13),
        )
        self.assertEqual(first.accepted_at, second.accepted_at)
        self.assertIsNotNone(first.accepted_at)

    def test_blocked_plan_cannot_be_accepted_through_repository(self) -> None:
        snapshot = PlaylistSnapshot(
            snapshot_id="snapshot-1",
            source_provider="spotify",
            source_playlist_id="playlist-1",
            entries=(SourcePlaylistEntry("occ-1", 0, "sp-1", EntryClassification.AMBIGUOUS),),
        )
        plan = build_copy_plan(
            snapshot,
            target_provider="youtube",
            target_playlist_name="Rock",
            policy=CopyPolicy.STRICT,
        )
        self.repository.save(plan, now=self.now)
        with self.assertRaises(PlanAcceptanceError):
            self.repository.accept(plan.digest, expected_digest=plan.digest, now=self.now)


if __name__ == "__main__":
    unittest.main()
