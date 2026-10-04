"""Write planned entries in order, reconciling uncertain provider outcomes."""

from __future__ import annotations

from symphonia.domain.models import CopyPlanEntry
from symphonia.domain.operations import OperationRecord
from symphonia.providers.writing import WriteOutcome

from .copy_execution_state import CopyRun


def copy_entries(run: CopyRun) -> OperationRecord:
    for entry in run.stored.plan.writable_entries:
        if (
            entry.occurrence_id in run.progress.confirmed_ids
            or entry.occurrence_id in run.progress.failed_steps
        ):
            continue
        stopped = _copy_entry(run, entry)
        if stopped is not None:
            return stopped

    run.checkpoint["confirmed_occurrences"] = run.progress.confirmed
    run.checkpoint["omitted_occurrences"] = [
        entry.occurrence_id for entry in run.stored.plan.omitted_entries
    ]
    run.checkpoint["issues"] = run.progress.issues
    terminal = "partial" if run.stored.plan.omitted_entries or run.progress.issues else "succeeded"
    return run.finish(terminal)


def _copy_entry(run: CopyRun, entry: CopyPlanEntry) -> OperationRecord | None:
    target_id = run.progress.target_id
    if target_id is None:
        raise RuntimeError("copy target must be confirmed before entry writes")
    step_key = f"{run.stored.plan.digest}:entry:{entry.occurrence_id}"
    if run.progress.unknown_step == entry.occurrence_id:
        return _reconcile_entry(run, entry, target_id, step_key)

    stopped = run.renew_or_stop()
    if stopped is not None:
        return stopped
    run.checkpoint["unknown_step"] = entry.occurrence_id
    if run.checkpoint_running().state != "running":
        return run.operation
    stopped = run.renew_or_stop()
    if stopped is not None:
        return stopped
    try:
        result = run.writer.add_entry(
            target_playlist_id=target_id,
            provider_track_id=entry.target_track_id or "",
            idempotency_key=step_key,
        )
    except Exception:
        return run.wait_for_user()

    if result.outcome is WriteOutcome.UNKNOWN_OUTCOME:
        return _reconcile_entry(run, entry, target_id, step_key)
    if result.outcome is WriteOutcome.RETRYABLE:
        run.checkpoint.pop("unknown_step", None)
        return run.schedule_retry()
    if result.outcome is WriteOutcome.RATE_LIMITED:
        run.checkpoint.pop("unknown_step", None)
        return run.schedule_rate_limit(result.retry_at)
    if result.outcome is WriteOutcome.PERMANENT_FAILURE:
        run.checkpoint.pop("unknown_step", None)
        run.progress.failed_steps.add(entry.occurrence_id)
        run.progress.issues.append({
            "step": entry.occurrence_id,
            "detail": result.detail or "permanent provider failure",
            "provider_code": result.provider_code,
        })
        run.checkpoint["issues"] = run.progress.issues
        if run.checkpoint_running().state != "running":
            return run.operation
        return None

    if run.confirm(entry.occurrence_id).state != "running":
        return run.operation
    return None


def _reconcile_entry(
    run: CopyRun, entry: CopyPlanEntry, target_id: str, step_key: str
) -> OperationRecord | None:
    stopped = run.renew_or_stop()
    if stopped is not None:
        return stopped
    try:
        reconciled = run.writer.reconcile_entry(
            target_playlist_id=target_id,
            provider_track_id=entry.target_track_id or "",
            idempotency_key=step_key,
        )
    except Exception:
        return run.wait_for_user()
    if not reconciled:
        return run.wait_for_user()
    if run.confirm(entry.occurrence_id).state != "running":
        return run.operation
    return None
