from __future__ import annotations

import unittest

from tools.storage_recovery_spike import run_spike


class StorageRecoverySpikeTests(unittest.TestCase):
    def test_spike_recovers_expired_lease_and_validates_backup(self) -> None:
        evidence = run_spike(operation_count=8)

        self.assertEqual(evidence["operation_count"], 8)
        self.assertEqual(evidence["recovered_operation_id"], "spike-operation-0")
        self.assertEqual(evidence["recovered_worker_id"], "worker-after-restart")
        self.assertEqual(evidence["recovered_state"], "succeeded")
        self.assertEqual(evidence["audit_event_count"], 4)
        self.assertTrue(evidence["backup_valid"])
        self.assertGreater(evidence["source_bytes"], 0)
        self.assertEqual(evidence["source_bytes"], evidence["backup_bytes"])

    def test_spike_bounds_disposable_fixture_size(self) -> None:
        with self.assertRaises(ValueError):
            run_spike(operation_count=0)
        with self.assertRaises(ValueError):
            run_spike(operation_count=10_001)


if __name__ == "__main__":
    unittest.main()
