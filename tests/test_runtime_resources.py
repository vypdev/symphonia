from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

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
            finally:
                resources.close()

            reopened = RuntimeResources.open(path)
            reopened.close()

    def test_empty_database_path_is_rejected_before_opening_stores(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeResources.open("   ")


if __name__ == "__main__":
    unittest.main()
