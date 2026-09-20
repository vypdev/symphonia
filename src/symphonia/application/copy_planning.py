"""Application service for the non-mutating copy planning use case."""

from __future__ import annotations

from dataclasses import dataclass

from symphonia.domain.models import CopyPlan, CopyPolicy, PlaylistSnapshot, build_copy_plan


@dataclass(frozen=True, slots=True)
class CopyPlanningService:
    """Coordinates normalized inputs without knowing provider implementations."""

    def plan(
        self,
        snapshot: PlaylistSnapshot,
        *,
        target_provider: str,
        target_playlist_name: str,
        target_visibility: str = "private",
        policy: CopyPolicy = CopyPolicy.STRICT,
    ) -> CopyPlan:
        return build_copy_plan(
            snapshot,
            target_provider=target_provider,
            target_playlist_name=target_playlist_name,
            target_visibility=target_visibility,
            policy=policy,
        )

