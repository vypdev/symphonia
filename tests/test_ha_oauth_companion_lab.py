"""Research fixture regression tests; actual Core/TLS/backup proofs are separate."""
import json
from pathlib import Path
import unittest

from tools.ha_oauth_companion_lab.app.server import Pairing


class CompanionLabFixtureTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.pair = Pairing("synthetic-challenge", clock=lambda: self.now)
        self.base = {"version": 1, "profile": "oauth", "epoch": 0}
        self.enroll = {**self.base, "op": "pair.enroll", "challenge": "synthetic-challenge"}

    def test_wrong_challenge_does_not_consume_the_valid_one(self):
        self.assertEqual(self.pair.request({**self.enroll, "challenge": "wrong"}, b"client"), 403)
        self.assertEqual(self.pair.request(self.enroll, b"client"), 200)

    def test_challenge_expires_at_exact_deadline(self):
        self.now = 400.0
        self.assertEqual(self.pair.request(self.enroll, b"client"), 403)
        self.assertIsNone(self.pair.peer)

    def test_enrollment_cannot_be_replayed_or_transferred(self):
        self.assertEqual(self.pair.request(self.enroll, b"client"), 200)
        self.assertEqual(self.pair.request(self.enroll, b"other"), 403)
        self.assertEqual(self.pair.request({**self.base, "op": "hello"}, b"other"), 403)

    def test_missing_client_identity_never_pairs(self):
        self.assertEqual(self.pair.request(self.enroll, None), 403)
        self.assertEqual(self.pair.request(self.enroll, b"client"), 200)

    def test_revocation_fences_the_old_certificate_and_epoch(self):
        self.pair.request(self.enroll, b"client")
        self.assertEqual(self.pair.request({**self.base, "op": "pair.revoke"}, b"client"), 200)
        self.assertEqual(self.pair.epoch, 1)
        for epoch in (0, 1):
            self.assertEqual(self.pair.request({**self.base, "op": "hello", "epoch": epoch}, b"client"), 403)

    def test_oauth_pair_never_acquires_playback_or_arbitrary_operations(self):
        self.pair.request(self.enroll, b"client")
        self.assertEqual(self.pair.request({**self.base, "op": "hello", "profile": "playback"}, b"client"), 403)
        for operation in ("player.command", "provider.request", "GET", ""):
            self.assertEqual(self.pair.request({**self.base, "op": operation}, b"client"), 403)

    def test_boolean_versions_and_epochs_are_not_integers(self):
        self.assertEqual(self.pair.request({**self.enroll, "version": True}, b"client"), 403)
        self.pair.request(self.enroll, b"client")
        self.assertEqual(self.pair.request({**self.base, "op": "hello", "epoch": False}, b"client"), 403)

    def test_non_objects_and_unknown_fields_are_rejected(self):
        for value in (None, [], "hello", 1):
            self.assertEqual(self.pair.request(value, b"client"), 400)
        self.assertEqual(self.pair.request({**self.enroll, "url": "https://example.invalid"}, b"client"), 400)

    def test_wrong_version_does_not_fall_back_to_plain_or_other_profile(self):
        self.assertEqual(self.pair.request({**self.enroll, "version": 2}, b"client"), 403)
        self.assertEqual(self.pair.request({**self.enroll, "profile": "unknown"}, b"client"), 403)

    def test_fixture_app_has_no_public_ports_mounts_or_core_permissions(self):
        path = Path(__file__).resolve().parents[1] / "tools/ha_oauth_companion_lab/app/config.fixture.json"
        data = json.loads(path.read_text())
        self.assertEqual(data["ports"], {})
        self.assertEqual(data["boot"], "manual")
        self.assertEqual(data["backup_exclude"], ["excluded/*"])
        for flag in ("homeassistant_api", "hassio_api", "auth_api", "docker_api", "host_network", "privileged", "map"):
            self.assertFalse(data.get(flag), flag)


if __name__ == "__main__":
    unittest.main()
