"""Untrusted Ingress input/artifact policy; real proxy/CSR proof is separate."""
from email.message import Message
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tools.ha_oauth_companion_lab import wire_lab_operator as operator
from tools.ha_oauth_companion_lab.enrollment_probe import Issuer

from tools.ha_oauth_companion_lab.wire_app import server as fixture


class WireBoundaryPolicyTests(unittest.TestCase):
    def handler(self,peer="172.30.32.2",*,user="a"*32,path="/api/hassio_ingress/synthetic-route"):
        value=object.__new__(fixture.IngressHandler)
        value.client_address=(peer,12345)
        value.headers=Message()
        value.headers["X-Remote-User-Id"]=user
        value.headers["X-Ingress-Path"]=path
        value.headers["Cookie"]="ingress_session="+"b"*128
        return value

    def test_core_peer_cannot_forge_complete_ingress_identity(self):
        with self.assertRaises(fixture.Locked):
            self.handler(peer="172.30.32.1").identity()

    def test_duplicate_actor_or_session_cookie_is_rejected(self):
        value=self.handler();value.headers["X-Remote-User-Id"]="c"*32
        with self.assertRaises(fixture.Locked):
            value.identity()
        value=self.handler();value.headers.replace_header("Cookie","ingress_session="+"b"*128+"; ingress_session="+"c"*128)
        with self.assertRaises(fixture.Locked):
            value.identity()

    def test_traversal_and_absolute_ingress_paths_are_rejected(self):
        for path in ("/api/hassio_ingress/../api","https://arbitrary.example.invalid/"):
            with self.assertRaises(fixture.Locked):
                self.handler(path=path).identity()

    def test_valid_context_binds_cookie_digest_and_ingress_path(self):
        first=self.handler().identity()
        second=self.handler(path="/api/hassio_ingress/another-route").identity()
        self.assertNotEqual(first,second)
        self.assertNotIn("b"*128,first)

    def test_duplicate_json_authority_field_is_not_last_value_wins(self):
        with self.assertRaises(fixture.Locked):
            fixture.unique_json(b'{"profile":"oauth","profile":"playback"}')

    def test_transport_fixture_is_hidden_and_requests_no_broad_permission(self):
        path=Path(__file__).parents[1]/"tools/ha_oauth_companion_lab/wire_app/app-metadata.fixture.json"
        value=json.loads(path.read_text())
        self.assertFalse(path.name.startswith("config."))
        self.assertEqual(value["ports"],{})
        self.assertEqual(value["map"],[])
        self.assertEqual(value["boot"],"manual")
        self.assertTrue(value["panel_admin"])
        for key in ("host_network","hassio_api","homeassistant_api"):
            self.assertFalse(value[key])


class WireOperatorTargetGuardTests(unittest.TestCase):
    def test_unknown_or_stopped_outer_lab_never_reaches_inner_docker(self):
        for details in (None,{"running":"false"},{"running":"true"}):
            with self.subTest(details=details), patch("tools.ha_app_lab._container_details",return_value=details), patch("tools.ha_app_lab._is_lab_container",return_value=False), patch.object(operator,"call") as command:
                with self.assertRaises(AssertionError):operator.guard()
                command.assert_not_called()

    def test_unexpected_core_image_refuses_all_fixture_operations(self):
        with patch("tools.ha_app_lab._container_details",return_value={"running":"true"}), patch("tools.ha_app_lab._is_lab_container",return_value=True), patch.object(operator,"call",return_value=SimpleNamespace(stdout=b"unexpected-image\n")) as command:
            with self.assertRaises(AssertionError):operator.guard()
            self.assertEqual(command.call_count,1)
            self.assertIn("inspect",command.call_args.args[0])


class RenewalAdmissionGuardTests(unittest.TestCase):
    def test_public_certificate_without_possession_proof_never_enters_transaction(self):
        from unittest.mock import Mock
        issuer=object.__new__(Issuer)
        issuer.validate_csr=Mock()
        issuer.db=Mock()
        for proof in (None,"not-base64!",{},"x"*257):
            with self.subTest(proof_type=type(proof).__name__), self.assertRaises(fixture.Locked):
                issuer.renew(b"public-certificate",0,"valid-csr",proof=proof)
        issuer.db.execute.assert_not_called()
