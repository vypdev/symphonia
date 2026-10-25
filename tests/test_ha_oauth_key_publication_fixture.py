"""Real file/SQL fences with fake AEAD; crypto/process-death proof is separate."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from tools.ha_oauth_companion_lab import key_publication_probe as fixture


class PublicationFenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "synthetic-publication"
        # These ordinary tests prove publication ordering, not encryption.
        self.addCleanup(patch.stopall)
        patch.object(fixture, "seal", side_effect=lambda key, data, aad: {
            "synthetic_payload": data.hex(), "synthetic_aad": aad.hex()}).start()
        def unseal(key, record, aad):
            if record["synthetic_aad"] != aad.hex():
                raise fixture.Locked("synthetic_aad_mismatch")
            return bytes.fromhex(record["synthetic_payload"])
        patch.object(fixture, "unseal", side_effect=unseal).start()
        fixture.Vault.create(self.root)
        self.vault = fixture.Vault(self.root)
        self.addCleanup(self.vault.close)

    def test_disconnect_fences_staged_publication_and_preserves_history(self):
        snapshot = self.vault.snapshot()
        candidate = self.vault.stage(fixture.NEW, snapshot)
        other = fixture.Vault(self.root)
        self.addCleanup(other.close)
        other.fence(disconnect=True)
        self.assertFalse(self.vault.activate(snapshot, candidate))
        self.assertIsNone(self.vault.read())
        self.assertEqual(other.db.execute("SELECT value FROM history").fetchone(), ("retained-synthetic-history",))
        self.vault.collect_quiescent()
        self.assertEqual(list((self.root / "records").iterdir()), [])

    def test_repair_fences_old_completion_without_removing_active_grant(self):
        snapshot = self.vault.snapshot()
        candidate = self.vault.stage(fixture.NEW, snapshot)
        self.vault.fence()
        self.assertFalse(self.vault.activate(snapshot, candidate))
        self.assertEqual(self.vault.read(), fixture.OLD)

    def test_two_sql_connections_racing_the_same_snapshot_activate_only_once(self):
        snapshot = self.vault.snapshot()
        candidates = [self.vault.stage(value, snapshot) for value in (b"one", b"two")]
        barrier = threading.Barrier(2)
        def activate(candidate):
            vault = fixture.Vault(self.root)
            try:
                barrier.wait(timeout=2)
                return vault.activate(snapshot, candidate)
            finally:
                vault.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(activate, candidates))
        self.assertEqual(sorted(results), [False, True])
        self.assertIn(self.vault.read(), (b"one", b"two"))
        self.vault.collect_quiescent()
        self.assertEqual(len(list((self.root / "records").iterdir())), 1)

    def test_failure_before_commit_rolls_back_and_leaves_collectible_orphan(self):
        snapshot = self.vault.snapshot()
        candidate = self.vault.stage(fixture.NEW, snapshot, rotate=True)
        def fail(point):
            if point == "before_commit":
                raise OSError("synthetic interruption")
        with self.assertRaises(OSError):
            self.vault.activate(snapshot, candidate, checkpoint=fail)
        self.assertEqual(self.vault.snapshot(), snapshot)
        self.assertEqual(self.vault.read(), fixture.OLD)
        self.vault.collect_quiescent()
        self.assertEqual(len(list((self.root / "keys").iterdir())), 1)

    def test_missing_key_blocks_rotation_without_generating_replacement(self):
        snapshot = self.vault.snapshot()
        (self.root / "keys" / snapshot[1]).unlink()
        with self.assertRaises(fixture.Locked):
            self.vault.stage(fixture.NEW, snapshot, rotate=True)
        self.assertEqual(list((self.root / "keys").iterdir()), [])
        self.assertEqual(self.vault.snapshot(), snapshot)

    def test_tampered_record_cannot_activate_or_collect_the_current_grant(self):
        snapshot = self.vault.snapshot()
        candidate = self.vault.stage(fixture.NEW, snapshot)
        path = self.root / "records" / candidate[1]
        record = json.loads(path.read_bytes())
        record["synthetic_aad"] = "wrong"
        path.write_text(json.dumps(record))
        with self.assertRaises(fixture.Locked):
            self.vault.activate(snapshot, candidate)
        self.assertEqual(self.vault.snapshot(), snapshot)
        self.assertEqual(self.vault.read(), fixture.OLD)
