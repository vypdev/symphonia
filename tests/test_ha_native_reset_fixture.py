"""Untrusted recovery-document parsing/binding; native HTTP proof is separate."""
import base64
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools.ha_oauth_companion_lab import native_reset_probe as fixture


class NativeResetDocumentTests(unittest.TestCase):
    def setUp(self):
        self.signer=object.__new__(fixture.NativeSigner)
        self.signer.installation="synthetic-installation"
        self.actor="synthetic-admin"
        self.request={"request_id":"a"*64,"installation":self.signer.installation,
            "actor":self.actor,"pair_epoch":0,"credential_epoch":2,"profile":"oauth-key-recovery",
            "purpose":"reset","expires":1020}
        self.clock=patch.object(fixture.time,"time",return_value=1000)
        self.clock.start();self.addCleanup(self.clock.stop)

    def reject(self,**changes):
        with self.assertRaises(fixture.Locked):
            self.signer.prepare(fixture.pack({**self.request,**changes}),self.actor)

    def test_valid_bounded_request_is_preserved(self):
        self.assertEqual(self.signer.prepare(fixture.pack(self.request),self.actor),self.request)

    def test_user_supplied_actor_cannot_replace_current_native_actor(self):
        self.reject(actor="another-admin")

    def test_different_installation_cannot_use_the_pair(self):
        self.reject(installation="another-installation")

    def test_changed_epoch_and_boolean_epoch_are_not_a_pair_identity(self):
        self.reject(pair_epoch=1)
        self.reject(pair_epoch=False)

    def test_credential_epoch_is_bounded_integer(self):
        self.reject(credential_epoch=-1)
        self.reject(credential_epoch=True)
        self.reject(credential_epoch=2**63)

    def test_unknown_or_structured_purpose_is_a_sanitized_refusal(self):
        self.reject(purpose="provider-revoke")
        self.reject(purpose={"reset":True})

    def test_expired_or_extended_deadline_cannot_be_signed(self):
        self.reject(expires=1000)
        self.reject(expires=1031)

    def test_request_identifier_cannot_carry_controls_or_paths(self):
        self.reject(request_id="\n"*64)
        self.reject(request_id="/"*64)

    def test_duplicate_json_field_is_rejected_before_binding(self):
        value=base64.b64encode(b'{"actor":"one","actor":"two"}').decode()
        with self.assertRaises(fixture.Locked):
            fixture.unpack(value)

    def test_oversized_or_nonbase64_document_is_rejected(self):
        for value in ("x"*4097,"invalid\\base64"):
            with self.assertRaises(fixture.Locked):
                fixture.unpack(value)

    def test_unknown_fields_and_profiles_cannot_expand_authority(self):
        self.reject(url="https://arbitrary.example.invalid")
        self.reject(profile="playback")


class NativeResetResumePolicyTests(unittest.TestCase):
    """Real SQL/files; explicitly fake AEAD and signature verification.

    Real native actor/signature proof belongs to the opt-in Core experiment.
    """
    def setUp(self):
        from tools.ha_oauth_companion_lab import recovery_probe
        self.recovery=recovery_probe
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        def seal(key,value,aad):
            return {"value":value.hex(),"aad":aad.hex()}
        def unseal(key,record,aad):
            if record["aad"]!=aad.hex():
                raise fixture.Locked("fake_codec_mismatch")
            return bytes.fromhex(record["value"])
        self.addCleanup(patch.stopall)
        patch.object(recovery_probe,"seal",side_effect=seal).start()
        patch.object(recovery_probe,"unseal",side_effect=unseal).start()
        patch.object(fixture.IngressStubConsumer,"_verify",return_value=None).start()
        root=Path(temporary.name)/"synthetic-resume"
        recovery_probe.RecoveryVault.create(root)
        self.vault=recovery_probe.RecoveryVault(root);self.addCleanup(self.vault.close)
        self.signer=SimpleNamespace(installation="synthetic-installation")

    def consumer(self):
        return fixture.IngressStubConsumer(self.vault,self.signer,"synthetic-admin")

    def submit(self,consumer,checkpoint=lambda point:None):
        document=fixture.pack({"request":consumer.request,"signature":"explicit-test-stub"})
        consumer.submit(document,actor=consumer.actor,browser=consumer.browser,csrf=consumer.csrf,
            origin="https://ha-reset.example.invalid",test_checkpoint=checkpoint)

    def interrupt(self):
        consumer=self.consumer()
        def fail(point):
            if point=="reset_key_staged":
                raise OSError("synthetic_publication_failure")
        with self.assertRaises(OSError):
            self.submit(consumer,fail)
        self.assertTrue(consumer.used)
        self.assertEqual(self.vault.phase(),"reset_pending")
        return consumer

    def test_failed_reset_needs_a_new_bound_resume_approval_and_preserves_history(self):
        first=self.interrupt()
        pending_epoch=self.vault.snapshot()[0]
        with self.assertRaises(fixture.Locked):
            self.submit(first)
        fresh=self.consumer()
        self.assertNotEqual(fresh.request["request_id"],first.request["request_id"])
        self.submit(fresh)
        self.assertEqual(self.vault.phase(),"unpaired")
        self.assertEqual(self.vault.snapshot()[0],pending_epoch)
        self.assertEqual(self.vault.read_all(),{})
        self.assertEqual(self.vault.db.execute("SELECT value FROM history").fetchone()[0],"retained-synthetic-history")
        with self.assertRaises(fixture.Locked):
            self.submit(fresh)

    def test_stale_resume_after_competing_success_cannot_generate_another_key(self):
        self.interrupt()
        first,stale=self.consumer(),self.consumer()
        self.submit(first)
        snapshot=self.vault.snapshot()
        keys=sorted(p.name for p in (self.vault.root/"keys").iterdir())
        with self.assertRaises(fixture.Locked):
            self.submit(stale)
        self.assertEqual(self.vault.snapshot(),snapshot)
        self.assertEqual(sorted(p.name for p in (self.vault.root/"keys").iterdir()),keys)
        self.assertFalse(stale.used)

    def test_postcommit_cleanup_requires_a_fresh_resume_without_rekeying(self):
        first=self.consumer()
        def fail(point):
            if point=='reset_after_commit':raise OSError('synthetic_cleanup_failure')
        with self.assertRaises(OSError):self.submit(first,fail)
        committed=self.vault.snapshot()
        self.assertTrue(self.vault.reset_retirement_pending())
        with self.assertRaises(fixture.Locked):self.submit(first)
        fresh=self.consumer();self.assertEqual(fresh.request['purpose'],'resume')
        self.submit(fresh)
        self.assertEqual(self.vault.snapshot(),committed)
        self.assertFalse(self.vault.needs_reset_resume())
        self.assertEqual(list((self.vault.root/'records').iterdir()),[])
        self.assertEqual({p.name for p in (self.vault.root/'keys').iterdir()},{committed[1]})
