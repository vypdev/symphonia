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
import sqlite3
import tempfile
import time
from typing import Any

from symphonia.runtime import RuntimeResources


BASE_TIME = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
MAX_OPERATION_COUNT = 10_000
MAX_PAYLOAD_BYTES_PER_OPERATION = 65_536
MAX_TOTAL_PAYLOAD_BYTES = 64 * 1024 * 1024


def run_spike(
    *, operation_count: int = 1000, payload_bytes: int = 0
) -> dict[str, Any]:
    """Run the disposable recovery scenario and return secret-free evidence."""

    if (
        isinstance(operation_count, bool)
        or not isinstance(operation_count, int)
        or not 1 <= operation_count <= MAX_OPERATION_COUNT
    ):
        raise ValueError(
            f"operation_count must be an integer between 1 and {MAX_OPERATION_COUNT}"
        )
    if (
        isinstance(payload_bytes, bool)
        or not isinstance(payload_bytes, int)
        or not 0 <= payload_bytes <= MAX_PAYLOAD_BYTES_PER_OPERATION
    ):
        raise ValueError(
            "payload_bytes must be an integer between 0 and "
            f"{MAX_PAYLOAD_BYTES_PER_OPERATION}"
        )
    total_payload_bytes = operation_count * payload_bytes
    if total_payload_bytes > MAX_TOTAL_PAYLOAD_BYTES:
        raise ValueError(
            f"total synthetic payload must not exceed {MAX_TOTAL_PAYLOAD_BYTES} bytes"
        )
    synthetic_padding = "x" * payload_bytes

    started = time.perf_counter()
    phase_ms: dict[str, float] = {}
    with tempfile.TemporaryDirectory(prefix="symphonia-storage-spike-") as directory:
        source_path = Path(directory) / "symphonia.sqlite3"
        backup_path = Path(directory) / "backup.sqlite3"

        phase_started = time.perf_counter()
        with RuntimeResources.open(str(source_path)) as resources:
            phase_ms["initial_runtime_open"] = round(
                (time.perf_counter() - phase_started) * 1000, 2
            )
            phase_started = time.perf_counter()
            for index in range(operation_count):
                payload = {"fixture_index": index}
                if synthetic_padding:
                    payload["synthetic_padding"] = synthetic_padding
                resources.operations.create(
                    operation_type="spike.copy",
                    idempotency_key=f"spike-key-{index}",
                    operation_id=f"spike-operation-{index}",
                    payload=payload,
                    now=BASE_TIME,
                )
            phase_ms["operation_creation"] = round(
                (time.perf_counter() - phase_started) * 1000, 2
            )
            phase_started = time.perf_counter()
            claimed = resources.operations.claim(
                "spike-operation-0",
                worker_id="worker-before-restart",
                now=BASE_TIME,
                lease_seconds=1,
            )
            phase_ms["initial_claim"] = round(
                (time.perf_counter() - phase_started) * 1000, 2
            )

        phase_started = time.perf_counter()
        with RuntimeResources.open(str(source_path)) as resources:
            phase_ms["restart_runtime_open"] = round(
                (time.perf_counter() - phase_started) * 1000, 2
            )
            phase_started = time.perf_counter()
            recovered = resources.operations.claim(
                claimed.operation_id,
                worker_id="worker-after-restart",
                now=BASE_TIME + timedelta(seconds=2),
                lease_seconds=30,
            )
            phase_ms["expired_lease_recovery"] = round(
                (time.perf_counter() - phase_started) * 1000, 2
            )
            recovered_worker_id = recovered.worker_id
            phase_started = time.perf_counter()
            completed = resources.operations.checkpoint(
                recovered.operation_id,
                worker_id="worker-after-restart",
                checkpoint={"recovered": True},
                now=BASE_TIME + timedelta(seconds=3),
                state="succeeded",
            )
            phase_ms["completion_checkpoint"] = round(
                (time.perf_counter() - phase_started) * 1000, 2
            )
            audit_event_count = len(resources.operations.events(recovered.operation_id))
            phase_started = time.perf_counter()
            resources.backup_to(str(backup_path))
            phase_ms["backup_creation"] = round(
                (time.perf_counter() - phase_started) * 1000, 2
            )

        source_bytes = source_path.stat().st_size
        backup_bytes = backup_path.stat().st_size
        phase_started = time.perf_counter()
        backup_valid = RuntimeResources.validate_backup(str(backup_path))
        phase_ms["backup_validation"] = round(
            (time.perf_counter() - phase_started) * 1000, 2
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "operation_count": operation_count,
            "payload_bytes_per_operation": payload_bytes,
            "total_synthetic_payload_bytes": total_payload_bytes,
            "sqlite_version": sqlite3.sqlite_version,
            "recovered_operation_id": recovered.operation_id,
            "recovered_worker_id": recovered_worker_id,
            "recovered_state": completed.state,
            "audit_event_count": audit_event_count,
            "source_bytes": source_bytes,
            "backup_bytes": backup_bytes,
            "backup_valid": backup_valid,
            "phase_ms": phase_ms,
            "elapsed_ms": elapsed_ms,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operations",
        type=int,
        default=1000,
        help=f"number of disposable queued operations to create (1-{MAX_OPERATION_COUNT})",
    )
    parser.add_argument(
        "--payload-bytes",
        type=int,
        default=0,
        help=(
            "synthetic padding bytes stored in each fixture operation "
            f"(0-{MAX_PAYLOAD_BYTES_PER_OPERATION}; 64 MiB total run cap)"
        ),
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run_spike(operation_count=args.operations, payload_bytes=args.payload_bytes),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
