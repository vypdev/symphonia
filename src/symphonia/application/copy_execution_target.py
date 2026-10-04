"""Create or reconcile the copy target before writing any playlist entries."""

from __future__ import annotations

from symphonia.domain.operations import OperationRecord
from symphonia.providers.writing import ProviderWriteError, WriteOutcome

from .copy_execution_state import CopyRun


def ensure_target(run: CopyRun) -> OperationRecord | None:
    """Return a stopped operation, or None when the target is confirmed."""

    target_key = f"{run.stored.plan.digest}:target"
    if run.progress.unknown_step == "target":
        stopped = run.renew_or_stop()
        if stopped is not None:
            return stopped
        try:
            target = run.writer.reconcile_target_playlist(idempotency_key=target_key)
        except Exception:
            return run.wait_for_user()
        if target is None or (
            run.progress.target_id is not None
            and target.provider_playlist_id != run.progress.target_id
        ):
            return run.wait_for_user()
        run.progress.target_id = target.provider_playlist_id
        run.checkpoint["target_playlist_id"] = run.progress.target_id
        run.checkpoint.pop("unknown_step", None)
        if run.checkpoint_running().state != "running":
            return run.operation
        run.progress.unknown_step = None

    if run.progress.target_id is not None:
        return None

    stopped = run.renew_or_stop()
    if stopped is not None:
        return stopped
    run.checkpoint["unknown_step"] = "target"
    if run.checkpoint_running().state != "running":
        return run.operation
    stopped = run.renew_or_stop()
    if stopped is not None:
        return stopped
    try:
        target = run.writer.ensure_target_playlist(
            provider=run.stored.plan.target_provider,
            name=run.stored.plan.target_playlist_name,
            visibility=run.stored.plan.target_visibility,
            idempotency_key=target_key,
        )
    except ProviderWriteError as error:
        if error.outcome is WriteOutcome.RETRYABLE:
            run.checkpoint.pop("unknown_step", None)
            return run.schedule_retry()
        if error.outcome is WriteOutcome.RATE_LIMITED:
            run.checkpoint.pop("unknown_step", None)
            return run.schedule_rate_limit(error.retry_at)
        if error.outcome is WriteOutcome.UNKNOWN_OUTCOME:
            stopped = run.renew_or_stop()
            if stopped is not None:
                return stopped
            try:
                target = run.writer.reconcile_target_playlist(idempotency_key=target_key)
            except Exception:
                return run.wait_for_user()
            if target is None:
                return run.wait_for_user()
        else:
            run.checkpoint.pop("unknown_step", None)
            run.progress.issues.append({
                "step": "target", "detail": error.detail,
                "provider_code": error.provider_code,
            })
            return run.finish("failed", checkpoint=run.checkpoint | {"issues": run.progress.issues})
    except Exception:
        return run.wait_for_user()

    run.progress.target_id = target.provider_playlist_id
    run.checkpoint["target_playlist_id"] = run.progress.target_id
    run.checkpoint.pop("unknown_step", None)
    if run.checkpoint_running().state != "running":
        return run.operation
    return None
