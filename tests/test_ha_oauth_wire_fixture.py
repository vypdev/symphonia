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


class ResetWireLifecycleTests(unittest.TestCase):
    def test_completed_reset_revocation_is_idempotent_and_never_rekeys(self):
        import sqlite3,tempfile
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/"issuer").mkdir()
            db=sqlite3.connect(root/"issuer/state.sqlite")
            db.executescript("CREATE TABLE pair(epoch INTEGER,serial TEXT,peer TEXT); INSERT INTO pair VALUES(0,'old','public'); CREATE TABLE challenge(value TEXT); INSERT INTO challenge VALUES('consumed');")
            db.commit();db.close()
            state=object.__new__(fixture.State);state.vault=Mock();state.vault.phase.return_value="unpaired"
            with patch.object(fixture,"ROOT",root):
                state.reconcile_reset();state.reconcile_reset()
            db=sqlite3.connect(root/"issuer/state.sqlite")
            self.assertEqual(db.execute("SELECT * FROM pair").fetchone(),(1,None,None))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM challenge").fetchone()[0],0);db.close()
            self.assertEqual({str(p.relative_to(root)) for p in root.rglob('*')},{"issuer","issuer/state.sqlite"})

    def test_pending_or_completed_reset_blocks_tls_before_peer_policy(self):
        from unittest.mock import Mock
        for phase in ("reset_pending","unpaired"):
            handler=object.__new__(fixture.TLSHandler);handler.path="/internal/ha-oauth/v1"
            state=Mock();state.vault.phase.return_value=phase;state.tls_active.return_value=False
            import threading
            state.authority_lock=threading.RLock()
            handler.server=SimpleNamespace(state=state);handler.data=lambda:{"op":"hello"}
            handler.send=Mock();handler.do_POST()
            self.assertEqual(handler.send.call_args.args[0],403)
            state.issuer.accepts.assert_not_called()

    def test_unpaired_page_never_returns_a_stale_bootstrap_challenge(self):
        from unittest.mock import Mock
        handler=object.__new__(fixture.IngressHandler);handler.path="/";handler.identity=lambda:("a","b","c")
        state=Mock();state.meta={"installation":"synthetic","expires":1};state.vault.phase.return_value="unpaired"
        state.public_signer.return_value=None;state.issuer=None;state.challenge="consumed-old-value"
        handler.server=SimpleNamespace(state=state,parsing_complete=Mock());handler.connection=object()
        handler.send=Mock();handler.do_GET()
        status,body=handler.send.call_args.args
        self.assertEqual(status,200);self.assertFalse(body["pairing_available"])
        self.assertNotIn("challenge",body);self.assertEqual(body["required_action"],"fresh_disposable_fixture")
