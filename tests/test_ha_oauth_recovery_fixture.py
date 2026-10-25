"""Actual file/SQLite recovery policy; fake AEAD, synthetic admission only."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from tools.ha_oauth_companion_lab import recovery_probe as fixture


class RecoveryFixtureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)/"synthetic-recovery"
        def seal(key, value, aad):
            return {"value":value.hex(), "aad":aad.hex(), "key":hashlib.sha256(key).hexdigest()}
        def unseal(key, record, aad):
            if record["aad"] != aad.hex() or record["key"] != hashlib.sha256(key).hexdigest():
                raise fixture.Locked("fake_codec_mismatch")
            return bytes.fromhex(record["value"])
        self.addCleanup(patch.stopall)
        patch.object(fixture,"seal",side_effect=seal).start()
        patch.object(fixture,"unseal",side_effect=unseal).start()
        fixture.RecoveryVault.create(self.root)
        self.vault = fixture.RecoveryVault(self.root)
        self.addCleanup(self.vault.close)

    def reopened(self):
        other = fixture.RecoveryVault(self.root)
        self.addCleanup(other.close)
        return other

    def test_live_owner_pins_staged_files_against_collection(self):
        owner = self.vault.admit()
        candidate = self.vault.stage_owner(owner,rotate=True)
        self.assertFalse(self.reopened().collect_quiescent())
        self.assertTrue((self.root/"keys"/candidate[0]).exists())
        self.assertTrue(self.vault.activate_owner(owner,candidate))
        self.assertEqual(self.vault.read_all(),fixture.NEW)

    def test_second_owner_cannot_enter_while_first_is_admitted(self):
        self.vault.admit()
        with self.assertRaises(fixture.Locked):
            self.reopened().admit()
        self.assertEqual(self.vault.db.execute("SELECT COUNT(*) FROM owners").fetchone()[0],1)

    def test_all_three_rotated_records_switch_together(self):
        snapshot = self.vault.snapshot()
        owner = self.vault.admit()
        candidate = self.vault.stage_owner(owner,rotate=True)
        self.assertEqual(self.reopened().read_all(),fixture.OLD)
        self.assertTrue(self.vault.activate_owner(owner,candidate))
        self.assertNotEqual(self.vault.snapshot()[1],snapshot[1])
        self.assertEqual(self.reopened().read_all(),fixture.NEW)
        self.assertTrue(self.vault.collect_quiescent())
        self.assertEqual(len(list((self.root/"keys").iterdir())),1)

    def test_partial_rotation_retains_every_old_record_and_recovers_orphans(self):
        owner = self.vault.admit()
        def fail(point):
            if point=="record_b":
                raise OSError("synthetic_write_failure")
        with self.assertRaises(OSError):
            self.vault.stage_owner(owner,rotate=True,checkpoint=fail)
        self.assertFalse(self.reopened().collect_quiescent())
        self.assertEqual(self.vault.read_all(),fixture.OLD)
        self.vault.recover_after_all_writers_exit()
        self.assertEqual(len(list((self.root/"records").iterdir())),3)

    def test_uncommitted_switch_rolls_back_all_connections(self):
        owner = self.vault.admit()
        candidate = self.vault.stage_owner(owner,rotate=True)
        def fail(point):
            if point=="before_commit":
                raise OSError("synthetic_sql_failure")
        with self.assertRaises(OSError):
            self.vault.activate_owner(owner,candidate,checkpoint=fail)
        self.assertEqual(self.reopened().read_all(),fixture.OLD)

    def test_two_sql_connections_cannot_activate_one_owner_twice(self):
        owner = self.vault.admit()
        candidates = [self.vault.stage_owner(owner,rotate=True) for _ in range(2)]
        barrier = threading.Barrier(2)
        def complete(candidate):
            vault = fixture.RecoveryVault(self.root)
            try:
                barrier.wait(timeout=3)
                return vault.activate_owner(owner,candidate)
            finally:
                vault.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(complete,candidates))
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(self.vault.read_all(),fixture.NEW)

    def test_epoch_change_fences_staged_publication(self):
        owner = self.vault.admit()
        candidate = self.vault.stage_owner(owner)
        self.reopened().db.execute("UPDATE state SET epoch=epoch+1")
        self.assertFalse(self.vault.activate_owner(owner,candidate))
        self.assertEqual(self.vault.read_all(),fixture.OLD)

    def test_one_corrupted_staged_record_cannot_activate_the_batch(self):
        owner = self.vault.admit()
        candidate = self.vault.stage_owner(owner,rotate=True)
        path = self.root/"records"/candidate[1]["b"]
        record = json.loads(path.read_bytes());record["aad"]="wrong";path.write_text(json.dumps(record))
        with self.assertRaises(fixture.Locked):
            self.vault.activate_owner(owner,candidate)
        self.assertEqual(self.vault.read_all(),fixture.OLD)

    def test_missing_active_key_refuses_rotation_without_reprovisioning(self):
        owner = self.vault.admit()
        snapshot = self.vault.snapshot()
        (self.root/"keys"/snapshot[1]).unlink()
        with self.assertRaises(fixture.Locked):
            self.vault.stage_owner(owner,rotate=True)
        self.assertEqual(list((self.root/"keys").iterdir()),[])
        self.assertEqual(self.vault.snapshot(),snapshot)

    def test_missing_new_key_preserves_the_active_old_generation(self):
        owner = self.vault.admit()
        candidate = self.vault.stage_owner(owner,rotate=True)
        (self.root/"keys"/candidate[0]).unlink()
        with self.assertRaises(fixture.Locked):
            self.vault.activate_owner(owner,candidate)
        self.assertEqual(self.vault.read_all(),fixture.OLD)

    def test_corrupt_active_record_blocks_recovery_without_erasing_evidence(self):
        snapshot = self.vault.snapshot()
        ref = json.loads(snapshot[2])["b"]
        path = self.root/"records"/ref
        record=json.loads(path.read_bytes());record["key"]="wrong";path.write_text(json.dumps(record))
        with self.assertRaises(fixture.Locked):
            self.vault.recover_after_all_writers_exit()
        self.assertEqual(self.vault.snapshot(),snapshot)
        self.assertTrue(path.exists())

    def test_unauthorized_reset_stub_changes_nothing(self):
        snapshot = self.vault.snapshot()
        with self.assertRaises(fixture.Locked):
            self.vault.explicit_reset()
        self.assertEqual(self.vault.snapshot(),snapshot)
        self.assertEqual(self.vault.read_all(),fixture.OLD)

    def test_explicit_reset_after_missing_keys_retains_history_and_requires_pairing(self):
        (self.root/"keys"/self.vault.snapshot()[1]).unlink()
        self.vault.explicit_reset(test_authorized=True)
        self.assertEqual(self.vault.phase(),"unpaired")
        self.assertEqual(self.vault.read_all(),{})
        self.assertEqual(self.vault.db.execute("SELECT value FROM history").fetchone()[0],"retained-synthetic-history")

    def test_reset_fence_survives_reopen_without_automatic_new_key(self):
        def fail(point):
            if point=="reset_fenced":
                raise OSError("synthetic_crash")
        with self.assertRaises(OSError):
            self.vault.explicit_reset(test_authorized=True,checkpoint=fail)
        keys = sorted(p.name for p in (self.root/"keys").iterdir())
        other = self.reopened()
        self.assertEqual(other.recover_after_all_writers_exit(),"reset_pending")
        self.assertEqual(sorted(p.name for p in (self.root/"keys").iterdir()),keys)
        with self.assertRaises(fixture.Locked):
            other.read_all()

    def test_staged_reset_key_needs_fresh_explicit_resume(self):
        def fail(point):
            if point=="reset_key_staged":
                raise OSError("synthetic_crash")
        with self.assertRaises(OSError):
            self.vault.explicit_reset(test_authorized=True,checkpoint=fail)
        self.assertFalse(self.vault.collect_quiescent())
        with self.assertRaises(fixture.Locked):
            self.vault.explicit_reset(resume=True)
        self.vault.explicit_reset(test_authorized=True,resume=True)
        self.assertEqual(self.vault.read_all(),{})
        self.assertTrue(self.vault.collect_quiescent())
        self.assertEqual(len(list((self.root/"keys").iterdir())),1)

    def test_health_observation_does_not_finish_pending_reset(self):
        def fail(point):
            if point=="reset_fenced":
                raise OSError("synthetic_crash")
        with self.assertRaises(OSError):
            self.vault.explicit_reset(test_authorized=True,checkpoint=fail)
        snapshot=self.vault.snapshot()
        for _ in range(3):
            self.assertEqual(self.reopened().phase(),"reset_pending")
        self.assertEqual(self.vault.snapshot(),snapshot)

    def test_reset_fences_an_already_staged_old_owner(self):
        owner=self.vault.admit();candidate=self.vault.stage_owner(owner,rotate=True)
        self.reopened().explicit_reset(test_authorized=True)
        self.assertFalse(self.vault.activate_owner(owner,candidate))
        self.assertEqual(self.vault.read_all(),{})

    def test_swapping_connection_references_fails_authenticated_binding(self):
        refs=json.loads(self.vault.snapshot()[2])
        self.vault.db.execute("UPDATE live SET reference=? WHERE name='b'",(refs["c"],))
        with self.assertRaises(fixture.Locked):
            self.vault.read_all()

    def test_missing_connection_row_cannot_be_treated_as_a_complete_rotation(self):
        self.vault.db.execute("DELETE FROM live WHERE name='c'")
        with self.assertRaises(fixture.Locked):
            self.vault.read_all()

    def test_partial_private_temporary_is_pinned_until_writer_exits(self):
        self.vault.admit()
        path=self.root/"records"/(".pending-"+"a"*32)
        path.write_bytes(b"partial synthetic ciphertext");path.chmod(0o600)
        self.assertFalse(self.reopened().collect_quiescent())
        self.assertTrue(path.exists())
        self.vault.recover_after_all_writers_exit()
        self.assertFalse(path.exists())
        self.assertEqual(self.vault.read_all(),fixture.OLD)

    def test_unreferenced_two_link_publication_is_collected_after_writer_exit(self):
        owner=self.vault.admit();candidate=self.vault.stage_owner(owner,rotate=True)
        orphan=self.root/"records"/candidate[1]["b"]
        pending=orphan.parent/(".pending-"+"a"*32)
        os.link(orphan,pending)
        self.assertFalse(self.vault.collect_quiescent())
        self.vault.recover_after_all_writers_exit()
        self.assertFalse(pending.exists());self.assertFalse(orphan.exists())
        self.assertEqual(self.vault.read_all(),fixture.OLD)

    def test_pending_link_to_active_record_locks_instead_of_silently_repairing(self):
        active=self.root/"records"/json.loads(self.vault.snapshot()[2])["b"]
        pending=active.parent/(".pending-"+"a"*32)
        os.link(active,pending)
        with self.assertRaises(fixture.Locked):
            self.vault.collect_quiescent()
        self.assertTrue(pending.exists());self.assertEqual(active.stat().st_nlink,2)

    def test_pending_symlink_is_retained_as_unsafe_evidence(self):
        pending=self.root/"records"/(".pending-"+"a"*32)
        key=self.root/"keys"/self.vault.snapshot()[1]
        pending.symlink_to(key)
        with self.assertRaises(fixture.Locked):
            self.vault.collect_quiescent()
        self.assertTrue(pending.is_symlink());self.assertTrue(key.exists())

    def test_successful_reset_retires_old_and_staged_secret_files(self):
        old_key=self.vault.snapshot()[1]
        owner=self.vault.admit();staged=self.vault.stage_owner(owner,rotate=True)
        self.vault.explicit_reset(test_authorized=True)
        self.assertFalse((self.root/'keys'/old_key).exists())
        self.assertFalse((self.root/'keys'/staged[0]).exists())
        self.assertEqual(list((self.root/'records').iterdir()),[])
        self.assertEqual({p.name for p in (self.root/'keys').iterdir()},{self.vault.snapshot()[1]})
        self.assertFalse(self.vault.reset_retirement_pending())
        self.assertFalse(self.vault.activate_owner(owner,staged))
        self.assertEqual(self.vault.db.execute('SELECT value FROM history').fetchone()[0],'retained-synthetic-history')

    def test_postcommit_retirement_resume_keeps_the_committed_identity(self):
        def fail(point):
            if point=='reset_records_retired':raise OSError('synthetic_retirement_failure')
        with self.assertRaises(OSError):self.vault.explicit_reset(test_authorized=True,checkpoint=fail)
        committed=self.vault.snapshot()
        other=self.reopened()
        self.assertEqual(other.phase(),'unpaired');self.assertTrue(other.needs_reset_resume())
        with self.assertRaises(fixture.Locked):other.explicit_reset(test_authorized=True)
        other.explicit_reset(test_authorized=True,resume=True)
        self.assertEqual(other.snapshot(),committed)
        self.assertEqual(list((self.root/'records').iterdir()),[])
        self.assertEqual({p.name for p in (self.root/'keys').iterdir()},{committed[1]})
        self.assertFalse(other.needs_reset_resume())
