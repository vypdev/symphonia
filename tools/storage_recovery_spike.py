"""Reproducible SQLite recovery/backup spike for the runtime foundation.

This is evidence tooling, not a production benchmark or a restore command. It
creates a disposable persistent store, simulates a worker restart with an
expired lease, and validates an online backup using the runtime's existing
preflight checks.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import time
from typing import Any

from symphonia.runtime import RuntimeResources


BASE_TIME = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def run_spike(*, operation_count: int = 1000) -> dict[str, Any]:
    """Run the disposable recovery scenario and return secret-free evidence."""

    if not 1 <= operation_count <= 10_000:
        raise ValueError("operation_count must be between 1 and 10000")

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="symphonia-storage-spike-") as directory:
        source_path = Path(directory) / "symphonia.sqlite3"
        backup_path = Path(directory) / "backup.sqlite3"

        with RuntimeResources.open(str(source_path)) as resources:
            for index in range(operation_count):
                resources.operations.create(
                    operation_type="spike.copy",
                    idempotency_key=f"spike-key-{index}",
                    operation_id=f"spike-operation-{index}",
                    payload={"fixture_index": index},
                    now=BASE_TIME,
                )
            claimed = resources.operations.claim(
                "spike-operation-0",
                worker_id="worker-before-restart",
                now=BASE_TIME,
                lease_seconds=1,
            )

        with RuntimeResources.open(str(source_path)) as resources:
            recovered = resources.operations.claim(
                claimed.operation_id,
                worker_id="worker-after-restart",
                now=BASE_TIME + timedelta(seconds=2),
                lease_seconds=30,
            )
            recovered_worker_id = recovered.worker_id
            completed = resources.operations.checkpoint(
                recovered.operation_id,
                worker_id="worker-after-restart",
                checkpoint={"recovered": True},
                now=BASE_TIME + timedelta(seconds=3),
                state="succeeded",
            )
            audit_event_count = len(resources.operations.events(recovered.operation_id))
            resources.backup_to(str(backup_path))

        source_bytes = source_path.stat().st_size
        backup_bytes = backup_path.stat().st_size
        backup_valid = RuntimeResources.validate_backup(str(backup_path))
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "operation_count": operation_count,
            "recovered_operation_id": recovered.operation_id,
            "recovered_worker_id": recovered_worker_id,
            "recovered_state": completed.state,
            "audit_event_count": audit_event_count,
            "source_bytes": source_bytes,
            "backup_bytes": backup_bytes,
            "backup_valid": backup_valid,
            "elapsed_ms": elapsed_ms,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operations",
        type=int,
        default=1000,
        help="number of disposable queued operations to create (1-10000)",
    )
    args = parser.parse_args()
    print(json.dumps(run_spike(operation_count=args.operations), sort_keys=True))


if __name__ == "__main__":
    main()
