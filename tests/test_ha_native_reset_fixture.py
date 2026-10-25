"""Untrusted recovery-document parsing/binding; native HTTP proof is separate."""
import base64
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
