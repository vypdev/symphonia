"""Ten ordinary HTTP/UI contracts; Core auth and Supervisor proof is separate."""
import ast
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import aiohttp
from aiohttp import web

from custom_components.symphonia_native_oauth_trial import bridge
from symphonia_native_oauth_trial.run import compose
from symphonia_native_oauth_trial.server import ingress_allowed


class RequestFixture(dict):
    def __init__(self, *, body=None, actor=None, path="/api/config/config_entries/flow/flow", method="POST"):
        super().__init__()
        if actor is not None:
            self["server_user"] = actor
        self.body = body if body is not None else {"confirm": True}
        self.path, self.method = path, method
        self.headers = {"X-Remote-User-Id": "admin", "X-Remote-User-Groups": "system-admin"}
    async def json(self):
        return self.body


def references():
    return {"schema": 1, "installation": "a" * 32, "pair_id": "b" * 32, "pair_epoch": 0,
            "credential_epoch": 0, "actor": "admin", "deadline": 2000000000,
            "app_slug": "local_symphonia_native_oauth_trial", "client_id": "opaque-public-client", "pin": "a" * 64,
            "material_hashes": {name: "c" * 64 for name in ("core.key", "ca.crt", "client.crt")}}


class NativeTrialHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from tests.test_native_oauth_trial_state import FakeProvider
        self.directory = tempfile.TemporaryDirectory()
        self.now = 1800000000
        self.server = compose(Path(self.directory.name), FakeProvider(), fresh=True, clock=lambda: self.now)

    async def asyncTearDown(self):
        self.server.state.close()
        self.directory.cleanup()

    def page_request(self, language="en"):
        return SimpleNamespace(remote="172.30.32.2", headers={"X-Ingress-Path": "/api/hassio_ingress/" + "synthetic" * 8,
             "X-Remote-User-Id": "admin", "X-Remote-User-Groups": "system-admin", "Accept-Language": language})

    async def test_http_C01_no_current_native_actor_admits_no_action(self):
        for request in (None, RequestFixture()):
            actor = bridge.validated_actor(request, "server_user")
            self.assertIsNone(actor)
            with self.assertRaises(bridge.BridgeError):
                await bridge.native_action(request, actor, "admin", "flow", {"confirm": True})

    async def test_http_C02_nonadmin_or_inactive_user_cannot_become_header_actor(self):
        for active, admin in ((True, False), (False, True)):
            request = RequestFixture(actor=SimpleNamespace(id="admin", is_active=active, is_admin=admin))
            actor = bridge.validated_actor(request, "server_user")
            self.assertIsNone(actor)
            with self.assertRaises(bridge.BridgeError):
                await bridge.native_action(request, actor, "admin", "flow", {"confirm": True})

    async def test_http_C03_only_new_native_request_body_confirms_not_saved_context(self):
        request = RequestFixture()
        self.assertEqual("admin", await bridge.native_action(request, "admin", "admin", "flow", {"confirm": True}))
        with self.assertRaises(bridge.BridgeError):
            await bridge.native_action(request, "admin", "admin", "flow", {"confirm": True})
        for wrong in (RequestFixture(path="/auth/external/callback", method="GET"),
                      RequestFixture(body={"confirm": False}), RequestFixture(body={"confirm": 1}),
                      RequestFixture(body={"confirm": True, "actor": "forged"})):
            with self.subTest(body=wrong.body), self.assertRaises(bridge.BridgeError):
                await bridge.native_action(wrong, "admin", "admin", "flow", {"confirm": True})
        with self.assertRaises(bridge.BridgeError):
            await bridge.native_action(RequestFixture(), "other-admin", "admin", "flow", {"confirm": True})
        self.assertEqual("admin", await bridge.native_action(RequestFixture(), "admin", "admin", "flow", {"confirm": True}))

    async def test_http_C04_actual_app_http_has_no_mutating_or_public_callback_surface(self):
        runner = web.AppRunner(self.server.ingress_app(), access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with aiohttp.ClientSession(trust_env=False) as client:
                for method, path, expected in (("GET", "/", 403), ("POST", "/", 405),
                                               ("GET", "/oauth/callback", 404), ("POST", "/oauth/callback", 404)):
                    async with client.request(method, f"http://127.0.0.1:{port}"+path,
                        headers={"X-Remote-User-Groups": "system-admin", "X-Remote-User-Id": "admin"}) as response:
                        self.assertEqual(expected, response.status)
                        self.assertNotIn(self.server.challenge.encode(), await response.read())
                async with client.get(f"http://127.0.0.1:{port}/health") as response:
                    self.assertEqual({"trial": True}, await response.json())
        finally:
            await runner.cleanup()

    async def test_http_C05_entry_allowlist_excludes_grants_codes_verifiers_and_private_keys(self):
        good = references()
        self.assertEqual(good, bridge.validate_reference(good))
        for field in ("token", "access_token", "refresh_token", "code", "verifier", "private_key"):
            with self.subTest(field=field), self.assertRaises(bridge.BridgeError):
                bridge.validate_reference({**good, field: "synthetic-secret-canary"})
        for changed in ({"installation": "../../other"}, {"deadline": True}, {"pair_epoch": True},
                        {"material_hashes": {"foreign.key": "c" * 64}}, {"binding": {"token": "canary"}}):
            with self.subTest(changed=changed), self.assertRaises(bridge.BridgeError):
                bridge.validate_reference({**good, **changed})
        self.assertNotIn("synthetic-secret-canary", json.dumps(good))
        for changed in ({"actor": "bad\nactor"}, {"client_id": " "}, {"client_id": "bad\nclient"},
                        {"retired": 1}, {"material_hashes": {name: "wrong" for name in good["material_hashes"]}}):
            with self.subTest(changed=changed), self.assertRaises(bridge.BridgeError):
                bridge.validate_reference({**good, **changed})
        for raw in (b"[]", b"", b"\xff", b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e9999}',
                    b'{' + b'"x":' + b'['*32 + b'0' + b']'*32 + b'}',
                    b'{' + b'"x":' + b'['*1100 + b'0' + b']'*1100 + b'}'):
            with self.subTest(size=len(raw)), self.assertRaises(bridge.BridgeError):
                bridge.document(raw)
        within = b'{"x":' + b'['*31 + b'0' + b']'*31 + b'}'
        self.assertIn("x", bridge.document(within))
        self.assertEqual({"x": [1.25]}, bridge.document(b'{"x":[1.25]}'))
        for block in (None, "{}", '{"installation":null}', "not-json"):
            with self.subTest(block=block), self.assertRaises(bridge.BridgeError):
                bridge.bootstrap(block)

    async def test_http_C06_architecture_forbids_default_token_and_broad_core_paths(self):
        root = Path(__file__).resolve().parents[1]
        forbidden = {"OAuth2Session", "async_resolve_external_data", "async_refresh_token", "async_oauth_create_entry"}
        for path in (root / "custom_components/symphonia_native_oauth_trial").glob("*.py"):
            tree = ast.parse(path.read_text())
            identifiers = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)} | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            self.assertFalse(identifiers & forbidden, path.name)
            imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            self.assertFalse(any(value.startswith(("homeassistant.components.spotify", "homeassistant.components.hassio")) for value in imports))
        for name in ("policy.py", "application.py"):
            tree = ast.parse((root / "symphonia_native_oauth_trial" / name).read_text())
            imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            self.assertFalse(any(value.startswith(("aiohttp", "homeassistant", "cryptography")) for value in imports))
            self.assertFalse(any(value in {"provider", "server", "store", "keys", "tls", "run"} for value in imports))

    async def test_http_C07_only_verified_ingress_boundary_can_show_bootstrap(self):
        request = self.page_request()
        self.assertTrue(ingress_allowed(request.remote, request.headers))
        for peer, changes in (("127.0.0.1", {}), ("172.30.32.3", {}),
                              ("172.30.32.2", {"X-Ingress-Path": "/"}),
                              ("172.30.32.2", {"X-Remote-User-Groups": "system-admin-evil"}),
                              ("172.30.32.2", {"X-Remote-User-Id": ""})):
            self.assertFalse(ingress_allowed(peer, {**request.headers, **changes}))
        rendered = await self.server.page(request)  # Named trusted-Ingress fixture, not proxy proof.
        self.assertIn(self.server.challenge, rendered.text)
        self.assertTrue(ingress_allowed("::ffff:172.30.32.2", request.headers))
        self.assertFalse(ingress_allowed("invalid-address", request.headers))

    async def test_http_C08_hostile_status_values_never_become_markup_or_secret_output(self):
        canary = "secret-canary<script>alert(1)</script>"
        with patch.object(self.server.state, "status", return_value={"phase": canary, "deadline": canary}):
            response = await self.server.page(self.page_request())
        self.assertNotIn(canary, response.text)
        self.assertNotIn("<script>", response.text)
        self.assertIn("locked", response.text)
        self.assertEqual("no-referrer", response.headers["Referrer-Policy"])
        self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])

    async def test_http_C09_localized_native_forms_and_semantic_readonly_status_disclose_limits(self):
        root = Path(__file__).resolve().parents[1] / "custom_components/symphonia_native_oauth_trial"
        english, spanish = (json.loads((root / "translations" / name).read_text()) for name in ("en.json", "es.json"))
        self.assertEqual(english, json.loads((root / "strings.json").read_text()))
        self.assertEqual(set(english["config"]["step"]), set(spanish["config"]["step"]))
        for language, expected in (("es", "Prueba OAuth"), ("en", "Symphonia OAuth trial")):
            rendered = await self.server.page(self.page_request(language))
            self.assertIn(expected.lower(), rendered.text.lower())
            self.assertIn("role='status'", rendered.text)
            self.assertIn("tabindex='0'", rendered.text)
            self.assertIn("width=device-width", rendered.text)
            self.assertIn("user-read-private", rendered.text)
            self.assertNotIn("<form", rendered.text)
        for language, action in (("en", "Reconfigure → Connect Spotify"), ("es", "Reconfigurar → Conectar Spotify")):
            with patch.object(self.server.state, "status", return_value={"phase": "paired", "deadline": self.server.state.meta()["deadline"]}):
                paired = await self.server.page(self.page_request(language))
            self.assertIn(action, paired.text)
            self.assertNotIn(self.server.challenge, paired.text)
            self.assertNotIn("<form", paired.text)
        for data in (english, spanish):
            self.assertIn("encrypted_core_backups", data["config"]["step"]["user"]["data"])
            self.assertIn("retire", data["config"]["step"])
            self.assertIn("retirement_unconfirmed", data["config"]["abort"])

    async def test_http_C10_status_is_observed_readonly_and_expiry_does_not_claim_revocation(self):
        original = self.server.state.meta()["deadline"]
        for _ in range(3):
            status = self.server.state.status(self.now)
            self.assertEqual({"phase": "unpaired", "deadline": original}, status)
        self.now = original
        response = await self.server.page(self.page_request())
        self.assertIn("expired", response.text)
        self.assertNotIn(self.server.challenge, response.text)
        self.assertNotIn("externally revoked", response.text)
        self.assertEqual(original, self.server.state.meta()["deadline"])
