"""Twelve distinct pure-policy cases from the native trial contract."""
from dataclasses import replace
import stat
import json
import unittest
from urllib.parse import parse_qs, urlencode

from symphonia_native_oauth_trial import policy as p


def binding():
    return p.Binding("install", "pair", "actor", "flow", "attempt", 0, 0,
                     "spotify", "opaque-id", p.PROFILE, p.REDIRECT, 2200)


class NativeTrialPolicyTests(unittest.TestCase):
    def test_pure_C01_opaque_client_survives_one_encoded_parameter(self):
        value = "opaque+client&part=?/not-hex"
        self.assertEqual(value, parse_qs(urlencode({"client_id": p.client_id(value)}))["client_id"][0])

    def test_pure_C02_invalid_client_never_echoes_input(self):
        for value in ("", "  ", "secret\ncanary", "café", "x" * 257, None):
            with self.subTest(kind=type(value).__name__), self.assertRaises(p.TrialError) as raised:
                p.client_id(value)
            self.assertEqual("invalid_client", str(raised.exception))

    def test_pure_C03_named_target_derives_only_fixed_alias(self):
        for prefix in ("local", "a1b2c3d4"):
            self.assertEqual(prefix + "-symphonia-native-oauth-trial",
                             p.app_alias(prefix + "_symphonia_native_oauth_trial"))
        self.assertEqual(8098, p.PORT)

    def test_pure_C04_target_injection_is_refused(self):
        for value in ("http://127.0.0.1", "local_symphonia_native_oauth_trial:80", "127.0.0.1",
                      "local_symphonia_native_oauth_trial/", "local_symphonia_native_oauth_trial_evil",
                      "symphonia_native_oauth_trial", None):
            with self.subTest(value=value), self.assertRaises(p.TrialError):
                p.app_alias(value)

    def test_pure_C05_redirect_is_exact(self):
        p.profile(p.REDIRECT, p.SCOPE)
        for value in (p.REDIRECT + "/", p.REDIRECT + "?a=b", p.REDIRECT.replace("https", "http"),
                      p.REDIRECT.replace("my.home-assistant.io", "evil.invalid")):
            with self.subTest(value=value), self.assertRaises(p.TrialError):
                p.profile(value, p.SCOPE)

    def test_pure_C06_scope_cannot_expand(self):
        for value in ("", None, "user-read-email", p.SCOPE + " user-read-playback-state", [p.SCOPE]):
            with self.subTest(value=value), self.assertRaises(p.TrialError):
                p.profile(p.REDIRECT, value)

    def test_pure_C07_bootstrap_is_single_use_and_expires_at_boundary(self):
        p.bootstrap(1000, 1300, False, 1299)
        for args in ((1000, 1300, False, 1300), (1000, 1300, True, 1001),
                     (1000, 1301, False, 1001), (1000, 1300, False, 999)):
            with self.subTest(args=args), self.assertRaises(p.TrialError):
                p.bootstrap(*args)

    def test_pure_C08_restart_keeps_original_deadline_and_rollback_locks(self):
        self.assertEqual(2200, p.lifetime(1000, 2200, 1200, 1250))
        for args in ((1000, 2200, 1200, 2200), (1000, 2200, 1200, 1199),
                     (1000, 2201, 1200, 1250), (1000, 2200, 1200, float("nan")),
                     (1000, 2200, 1200, True)):
            with self.subTest(args=args), self.assertRaises(p.TrialError):
                p.lifetime(*args)

    def test_pure_C09_typed_envelopes_reject_extra_fields_and_boolean_epochs(self):
        document = {"version": 1, "op": "attempt.complete", "binding": binding().wire()}
        self.assertEqual(document, p.envelope(document))
        variants = [{**document, "version": True}, {**document, "version": 2}, {**document, "extra": "no"},
                    {**document, "binding": {}},
                    {**document, "binding": {**binding().wire(), "provider": "wrong"}},
                    {**document, "binding": {**binding().wire(), "pair_epoch": True}},
                    {**document, "binding": {**binding().wire(), "flow": "x" * 129}},
                    {"version": 1, "op": "attempt.cancel", "binding": binding().wire(), "reason": "retry"},
                    {"version": 1, "op": "pair.enroll", "actor": "ok", "csr": 4, "challenge": "challenge"},
                    {"version": 1, "op": "attempt.start", "binding": binding().wire(), "verifier": "short"}]
        for value in variants:
            with self.subTest(value=value), self.assertRaises(p.TrialError):
                p.envelope(value)
        for kind in ("list", "dict"):
            value = 0
            for _ in range(31):
                value = [value] if kind == "list" else {"nested": value}
            accepted = json.dumps({"root": value}).encode()
            self.assertIn("root", p.strict_json(accepted, 16384))
            refused = json.dumps({"extra": {"root": value}}).encode()
            with self.assertRaises(p.TrialError):
                p.strict_json(refused, 16384)
        self.assertEqual({"x": [1.25]}, p.strict_json(b'{"x":[1.25]}', 16384))
        with self.assertRaises(p.TrialError):
            p.strict_json(b'{"x":[1e9999]}', 16384)

    def test_pure_C10_private_metadata_rejects_unsafe_files(self):
        good = dict(mode=stat.S_IFREG | 0o600, owner=10001, expected_owner=10001, links=1, size=32)
        p.private_file(**good)
        for change in ({"mode": stat.S_IFLNK | 0o600}, {"mode": stat.S_IFIFO | 0o600},
                       {"mode": stat.S_IFREG | 0o644}, {"owner": 0}, {"links": 2},
                       {"size": 0}, {"size": 16385}):
            with self.subTest(change=change), self.assertRaises(p.TrialError):
                p.private_file(**{**good, **change})

    def test_pure_C11_operations_cannot_acquire_other_authority(self):
        self.assertEqual("hello", p.envelope({"version": 1, "op": "hello"})["op"])
        for operation in ("playback", "core.request", "http", "pair.renew", "reset", None, []):
            with self.subTest(operation=operation), self.assertRaises(p.TrialError):
                p.envelope({"version": 1, "op": operation})

    def test_pure_C12_every_immutable_binding_field_is_checked(self):
        original = binding()
        original.require(p.Binding.parse(original.wire()), 1200)
        for name, value in original.wire().items():
            other = replace(original, **{name: value + 1 if type(value) is int else value + "changed"})
            with self.subTest(field=name), self.assertRaises(p.TrialError):
                original.require(other, 1200)
        with self.assertRaises(p.TrialError):
            original.require(original, 2200)
        for now in (True, float("nan"), -1, 2**54):
            with self.subTest(now=now), self.assertRaises(p.TrialError):
                original.require(original, now)
