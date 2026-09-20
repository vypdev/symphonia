from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone

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


if __name__ == "__main__":
    unittest.main()
