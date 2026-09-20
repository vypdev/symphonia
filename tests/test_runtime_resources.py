from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
import sqlite3

from symphonia.infrastructure import OperationRepository
from symphonia.runtime import RuntimeResources


class RuntimeResourcesTests(unittest.TestCase):
    def test_open_creates_all_durable_store_schemas_and_closes_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "symphonia.sqlite3")
            resources = RuntimeResources.open(path)
            try:
                tables = {
                    row[0]
                    for row in resources.operations._connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                self.assertIn("operations", tables)
                self.assertIn("provider_connections", tables)
                self.assertIn("copy_plans", tables)
                self.assertIn("playlist_snapshots", tables)
                self.assertIn("authorization_attempts", tables)
                self.assertIn("resolution_decisions", tables)
                self.assertTrue(resources.healthcheck())
            finally:
                resources.close()

            reopened = RuntimeResources.open(path)
            reopened.close()

    def test_empty_database_path_is_rejected_before_opening_stores(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeResources.open("   ")

    def test_readiness_fails_closed_when_one_store_is_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            resources = RuntimeResources.open(str(Path(directory) / "symphonia.sqlite3"))
            try:
                resources.plans.close()
                self.assertFalse(resources.healthcheck())
            finally:
                resources.resolutions.close()
                resources.projections.close()
                resources.authorization.close()
                resources.connections.close()
                resources.operations.close()

    def test_backup_to_copies_a_consistent_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = str(Path(directory) / "symphonia.sqlite3")
            backup_path = str(Path(directory) / "backup.sqlite3")
            resources = RuntimeResources.open(source_path)
            try:
                created = resources.operations.create(
                    operation_type="test",
                    idempotency_key="backup-key",
                    payload={"value": "persisted"},
                    now=datetime(2026, 9, 20, tzinfo=timezone.utc),
                )
                resources.backup_to(backup_path)
            finally:
                resources.close()

            self.assertTrue(RuntimeResources.validate_backup(backup_path))

            backup = OperationRepository(backup_path)
            try:
                restored = backup.get(created.operation_id)
                self.assertEqual(restored.payload, {"value": "persisted"})
                self.assertEqual(len(backup.events(created.operation_id)), 1)
            finally:
                backup.close()

    def test_backup_to_rejects_the_live_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = str(Path(directory) / "symphonia.sqlite3")
            resources = RuntimeResources.open(source_path)
            try:
                with self.assertRaises(ValueError):
                    resources.backup_to(source_path)
            finally:
                resources.close()

    def test_backup_to_rejects_in_memory_runtime_and_destination(self) -> None:
        resources = RuntimeResources.open(":memory:")
        try:
            with self.assertRaises(ValueError):
                resources.backup_to("backup.sqlite3")
        finally:
            resources.close()

        with tempfile.TemporaryDirectory() as directory:
            source_path = str(Path(directory) / "symphonia.sqlite3")
            resources = RuntimeResources.open(source_path)
            try:
                with self.assertRaises(ValueError):
                    resources.backup_to(":memory:")
            finally:
                resources.close()

    def test_backup_to_replaces_an_existing_destination_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = str(Path(directory) / "symphonia.sqlite3")
            backup_path = Path(directory) / "backup.sqlite3"
            backup_path.write_text("old backup", encoding="utf-8")
            resources = RuntimeResources.open(source_path)
            try:
                resources.operations.create(
                    operation_type="test",
                    idempotency_key="atomic-backup",
                    payload={},
                    now=datetime(2026, 9, 20, tzinfo=timezone.utc),
                )
                resources.backup_to(str(backup_path))
            finally:
                resources.close()

            self.assertTrue(RuntimeResources.validate_backup(str(backup_path)))

    def test_backup_to_fails_closed_when_a_store_is_unhealthy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = str(Path(directory) / "symphonia.sqlite3")
            destination_path = str(Path(directory) / "backup.sqlite3")
            resources = RuntimeResources.open(source_path)
            try:
                resources.plans.close()
                with self.assertRaisesRegex(RuntimeError, "unhealthy"):
                    resources.backup_to(destination_path)
                self.assertFalse(Path(destination_path).exists())
            finally:
                resources.resolutions.close()
                resources.projections.close()
                resources.authorization.close()
                resources.connections.close()
                resources.operations.close()

    def test_validate_backup_rejects_missing_or_corrupt_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / "missing.sqlite3")
            corrupt = Path(directory) / "corrupt.sqlite3"
            corrupt.write_text("not a sqlite database", encoding="utf-8")

            self.assertFalse(RuntimeResources.validate_backup(missing))
            self.assertFalse(RuntimeResources.validate_backup(str(corrupt)))
            with self.assertRaises(ValueError):
                RuntimeResources.validate_backup("   ")

    def test_validate_backup_rejects_schema_shaped_but_incompatible_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partial.sqlite3"
            connection = sqlite3.connect(path)
            try:
                for table in (
                    "operations", "operation_events", "copy_plans", "provider_connections",
                    "authorization_attempts", "playlist_snapshots", "playlist_snapshot_entries",
                    "current_playlist_snapshots", "resolution_decisions",
                ):
                    connection.execute(f"CREATE TABLE {table} (placeholder TEXT)")
                connection.commit()
            finally:
                connection.close()

            self.assertFalse(RuntimeResources.validate_backup(str(path)))

    def test_diagnostics_combine_safe_queue_and_operation_views(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            resources = RuntimeResources.open(str(Path(directory) / "symphonia.sqlite3"))
            try:
                resources.operations.create(
                    operation_type="test",
                    idempotency_key="diagnostic-key",
                    payload={"plan_digest": "must-not-appear"},
                    now=datetime(2026, 9, 20, tzinfo=timezone.utc),
                )
                diagnostics = resources.diagnostics(
                    now=datetime(2026, 9, 20, 0, 0, 1, tzinfo=timezone.utc),
                    operation_limit=1,
                    event_limit=1,
                )
                self.assertTrue(diagnostics["ready"])
                self.assertEqual(diagnostics["queue"]["total"], 1)
                self.assertEqual(
                    diagnostics["connections"],
                    {"total": 0, "by_provider": {}, "expired_count": 0},
                )
                self.assertEqual(
                    diagnostics["projections"],
                    {
                        "snapshot_count": 0,
                        "current_playlist_count": 0,
                        "entry_count": 0,
                        "unavailable_entry_count": 0,
                        "latest_published_at": None,
                    },
                )
                self.assertEqual(diagnostics["resolutions"], {"total": 0, "by_action": {}})
                self.assertEqual(len(diagnostics["operations"]), 1)
                self.assertNotIn("must-not-appear", str(diagnostics))
                with self.assertRaises(ValueError):
                    resources.diagnostics(now=datetime(2026, 9, 20, tzinfo=timezone.utc), operation_limit=0)
            finally:
                resources.close()

    def test_diagnostics_fail_closed_when_a_store_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            resources = RuntimeResources.open(str(Path(directory) / "symphonia.sqlite3"))
            resources.plans.close()
            try:
                self.assertEqual(
                    resources.diagnostics(now=datetime(2026, 9, 20, tzinfo=timezone.utc)),
                    {"ready": False},
                )
            finally:
                resources.resolutions.close()
                resources.projections.close()
                resources.authorization.close()
                resources.connections.close()
                resources.operations.close()

    def test_diagnostics_fail_closed_if_a_store_fails_after_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            resources = RuntimeResources.open(str(Path(directory) / "symphonia.sqlite3"))
            try:
                original = resources.operations.queue_summary

                def fail_after_readiness(*, now):
                    raise RuntimeError("internal database detail")

                resources.operations.queue_summary = fail_after_readiness  # type: ignore[method-assign]
                self.assertEqual(
                    resources.diagnostics(now=datetime(2026, 9, 20, tzinfo=timezone.utc)),
                    {"ready": False},
                )
                resources.operations.queue_summary = original  # type: ignore[method-assign]
            finally:
                resources.close()


if __name__ == "__main__":
    unittest.main()
