"""Validate persisted copy progress before any external provider write."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from symphonia.domain.models import CopyPlan


@dataclass(slots=True)
class CopyProgress:
    confirmed: list[str]
    confirmed_ids: set[str]
    issues: list[Any]
    failed_steps: set[str]
    target_id: str | None
    unknown_step: str | None


def parse_copy_progress(plan: CopyPlan, checkpoint: dict[str, Any]) -> CopyProgress | str:
    """Return validated progress or the public recovery code for a corrupt checkpoint."""

    writable_entries = plan.writable_entries
    writable_ids = {entry.occurrence_id for entry in writable_entries}
    raw_confirmed = checkpoint.get("confirmed_occurrences", [])
    raw_issues = checkpoint.get("issues", [])
    target_id = checkpoint.get("target_playlist_id")
    unknown_step = checkpoint.get("unknown_step")
    if (
        not isinstance(raw_confirmed, list)
        or not all(isinstance(item, str) for item in raw_confirmed)
        or not isinstance(raw_issues, list)
        or (target_id is not None and (not isinstance(target_id, str) or not target_id.strip()))
    ):
        return "invalid_copy_checkpoint"
    confirmed = list(raw_confirmed)
    issues = list(raw_issues)
    confirmed_ids = set(confirmed)
    issue_steps = [issue.get("step") if isinstance(issue, dict) else None for issue in issues]
    if any(not isinstance(step, str) or step not in writable_ids for step in issue_steps):
        return "invalid_copy_checkpoint"
    failed_steps = set(issue_steps)
    processed_ids = confirmed_ids | failed_steps
    if (
        len(confirmed_ids) != len(confirmed)
        or not confirmed_ids <= writable_ids
        or confirmed != [entry.occurrence_id for entry in writable_entries if entry.occurrence_id in confirmed_ids]
        or len(failed_steps) != len(issue_steps)
        or confirmed_ids & failed_steps
        or processed_ids != {
            entry.occurrence_id for entry in writable_entries[:len(processed_ids)]
        }
    ):
        return "invalid_copy_checkpoint"

    if target_id is None and confirmed:
        return "invalid_target_checkpoint"

    if unknown_step is not None:
        first_unconfirmed = next(
            (
                entry.occurrence_id
                for entry in writable_entries
                if entry.occurrence_id not in confirmed_ids and entry.occurrence_id not in failed_steps
            ),
            None,
        )
        if unknown_step != "target" and (
            not isinstance(unknown_step, str)
            or unknown_step not in writable_ids
            or unknown_step in confirmed_ids
            or unknown_step != first_unconfirmed
            or target_id is None
        ):
            return "invalid_unknown_step_checkpoint"
        if unknown_step == "target" and target_id is None and confirmed:
            return "invalid_unknown_step_checkpoint"

    return CopyProgress(confirmed, confirmed_ids, issues, failed_steps, target_id, unknown_step)
