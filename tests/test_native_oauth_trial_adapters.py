"""Provider fixture contracts and actual local AEAD/filesystem observations."""
from dataclasses import replace
import asyncio
import base64
import hashlib
import secrets
import socket
import ssl
import sqlite3
import time
import aiohttp
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from urllib.parse import urlencode
from multidict import MultiDict

from custom_components.symphonia_native_oauth_trial import bridge as core_bridge
from custom_components.symphonia_native_oauth_trial.keys import CoreKeys, KeyUnavailable
from symphonia_native_oauth_trial.run import compose

from symphonia_native_oauth_trial.application import Grant
from symphonia_native_oauth_trial.keys import PrivateFiles, Vault
from symphonia_native_oauth_trial.policy import Binding, PROFILE, REDIRECT, TrialError
from symphonia_native_oauth_trial.provider import BODY_LIMIT, ME, TOKEN, Response, Spotify, FixedHTTP


def binding():
    return Binding("installation", "pair", "admin", "flow", "attempt", 0, 0,
                   "spotify", "opaque-client", PROFILE, REDIRECT, 2200)


def token(**changes):
    return {"access_token": "access-canary", "refresh_token": "refresh-canary",
            "token_type": "Bearer", "scope": "user-read-private", "expires_in": 3600, **changes}


class FixtureHTTP:
    def __init__(self, document=None, *, status=200, raw=None):
        self.response = Response(status, raw if raw is not None else json.dumps(document).encode())
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


class NativeTrialProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_C01_new_authorizer_is_created_and_redundant_verifier_cleared(self):
        instances = []
        class PublicAuthorizer:
            redirect_uri = REDIRECT
            def __init__(self, hass, domain, client_id, authorize_url, token_url, client_secret=""):
                self.code_verifier = secrets.token_urlsafe(48)
                self.client = client_id
                instances.append(self)
                self.assert_no_secret = client_secret == ""
            async def async_generate_authorize_url(self, flow_id):
                challenge = base64.urlsafe_b64encode(hashlib.sha256(self.code_verifier.encode()).digest()).rstrip(b"=").decode()
                return "https://accounts.spotify.com/authorize?" + urlencode({"response_type": "code",
                    "client_id": self.client, "redirect_uri": self.redirect_uri, "state": "synthetic-state",
                    "code_challenge_method": "S256", "code_challenge": challenge})
        first = await core_bridge.authorize(None, "flow1", "opaque+id&part", PublicAuthorizer)
        second = await core_bridge.authorize(None, "flow2", "opaque+id&part", PublicAuthorizer)
        self.assertNotEqual(first[1], second[1])
        self.assertNotEqual(first[0], second[0])
        self.assertTrue(all(item.code_verifier == "" and item.assert_no_secret for item in instances))
        with patch.object(PublicAuthorizer, "redirect_uri", "https://wrong.invalid"):
            with self.assertRaises(core_bridge.BridgeError):
                await core_bridge.authorize(None, "flow", "public", PublicAuthorizer)
        self.assertEqual("", instances[-1].code_verifier)

    async def test_adapter_C02_only_real_route_shaped_bounded_return_is_staged(self):
        value = {"state": {"flow_id": "flow", "redirect_uri": REDIRECT}, "code": "synthetic-code"}
        request = SimpleNamespace(path="/auth/external/callback", method="GET", query=MultiDict({"state": "core-signed-state-fixture", "code": "synthetic-code"}))
        self.assertEqual(("stage", "synthetic-code"), core_bridge.callback_input(request, "flow", value))
        variants = [None, SimpleNamespace(**{**vars(request), "path": "/api/config/config_entries/flow/flow"}),
                    SimpleNamespace(**{**vars(request), "method": "POST"}),
                    SimpleNamespace(**{**vars(request), "query": MultiDict([("state", "s"), ("code", "synthetic-code"), ("code", "other")])})]
        for changed in variants:
            with self.subTest(request=changed is None), self.assertRaises(core_bridge.BridgeError):
                core_bridge.callback_input(changed, "flow", value)
        for changed in ({**value, "error": "denied"}, {"state": {**value["state"], "actor": "forged"}, "code": "synthetic-code"},
                        {**value, "code": "x" * 2049}, {**value, "code": "bad\ncode"}, {"state": value["state"]}):
            with self.subTest(keys=sorted(changed)), self.assertRaises(core_bridge.BridgeError):
                core_bridge.callback_input(request, "flow", changed)
    async def test_adapter_C05_strict_bounded_responses_have_closed_errors(self):
        for raw in (b'{"access_token":"secret-canary","access_token":"second"}',
                    b'\xff', b'[]', b'{"secret":"'+b'x' * BODY_LIMIT+b'"}',
                    b'{"token_type":NaN}', b'{"a":'+b'['*1100+b'0'+b']'*1100+b'}'):
            port = FixtureHTTP(raw=raw)
            with self.subTest(size=len(raw)), self.assertRaises(TrialError) as raised:
                await Spotify(port).exchange(binding(), "code", "v" * 64)
            self.assertNotIn("secret-canary", str(raised.exception))
            self.assertNotIn("secret", repr(port.response))
        for changes in ({"expires_in": True}, {"expires_in": 0}, {"expires_in": 86401},
                        {"access_token": []}, {"refresh_token": "bad\ncanary"}, {"token_type": None}):
            with self.subTest(changes=changes), self.assertRaises(TrialError):
                await Spotify(FixtureHTTP(token(**changes))).exchange(binding(), "code", "v" * 64)

    async def test_adapter_C06_only_explicit_verified_exchange_scope_activates(self):
        port = FixtureHTTP(token())
        grant = await Spotify(port, lambda: 1000).exchange(binding(), "synthetic-code", "v" * 64)
        self.assertEqual(4600, grant.expires)
        self.assertEqual(("POST", TOKEN), port.calls[0][:2])
        self.assertEqual({"grant_type", "code", "code_verifier", "client_id", "redirect_uri"},
                         set(port.calls[0][2]["data"]))
        for scope in (None, "user-read-email", "user-read-private user-read-email", "user-read-private user-read-private"):
            with self.subTest(scope=scope), self.assertRaises(TrialError) as raised:
                await Spotify(FixtureHTTP(token(scope=scope))).exchange(binding(), "code", "v" * 64)
            self.assertEqual("invalid_scope", raised.exception.reason)

    async def test_adapter_C07_account_id_is_only_stable_identity(self):
        grant = Grant("access", "refresh", 2000)
        first = await Spotify(FixtureHTTP({"account_id": "opaque-stable-account"})).account(binding(), grant)
        same = await Spotify(FixtureHTTP({"account_id": "opaque-stable-account", "id": "changed"})).account(binding(), grant)
        other = await Spotify(FixtureHTTP({"account_id": "other-account"})).account(binding(), grant)
        self.assertEqual(first, same)
        self.assertNotEqual(first, other)
        for value in (None, "", {}, "x" * 257, "bad\nidentity"):
            port = FixtureHTTP({"account_id": value, "id": "legacy", "display_name": "Name", "email": "email"})
            with self.subTest(value=value), self.assertRaises(TrialError) as raised:
                await Spotify(port).account(binding(), grant)
            self.assertEqual("unsupported_account", raised.exception.reason)
            self.assertEqual(("GET", ME), port.calls[0][:2])

    async def test_adapter_C08_omitted_refresh_replacement_retains_verified_material(self):
        document = token(access_token="new-access")
        del document["refresh_token"], document["scope"]
        port = FixtureHTTP(document)
        grant = await Spotify(port, lambda: 1000).refresh(binding(), Grant("old-access", "old-refresh", 1100))
        self.assertEqual(("new-access", "old-refresh"), (grant.access, grant.refresh))
        self.assertEqual({"grant_type": "refresh_token", "refresh_token": "old-refresh", "client_id": "opaque-client"},
                         port.calls[0][2]["data"])
        self.assertNotIn("old-refresh", repr(grant))

    async def test_adapter_C09_invalid_grant_is_fixed_and_not_retried(self):
        port = FixtureHTTP({"error": "invalid_grant", "error_description": "secret-error-canary"}, status=400)
        with self.assertRaises(TrialError) as raised:
            await Spotify(port).refresh(binding(), Grant("access", "refresh", 2000))
        self.assertEqual("invalid_grant", str(raised.exception))
        self.assertEqual(1, len(port.calls))

    async def test_adapter_C10_fixed_bounded_transport_closes_streams_and_real_stalled_dns(self):
        # Controlled response adapter covers framing/errors; actual c-ares below
        # covers cancellation without external DNS or a detached resolver thread.
        sessions, resolvers = [], []
        class ResolverFixture:
            def __init__(self):
                self.closed = False
                resolvers.append(self)
            async def close(self):
                self.closed = True
        class BodyFixture:
            def __init__(self, body):
                self.body, self.reads = body, 0
            async def read(self, maximum):
                self.reads += 1
                size = min(maximum, 3 if len(self.body) < 1000 else maximum)
                result, self.body = self.body[:size], self.body[size:]
                return result
        class ResponseFixture:
            def __init__(self, status, headers, body):
                self.status, self.headers, self.content = status, headers, BodyFixture(body)
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
        class SessionFixture:
            def __init__(self, response, fail, **kwargs):
                self.response, self.fail, self.options, self.closed = response, fail, kwargs, False
                sessions.append(self)
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                await self.options["connector"].close()
                self.closed = True
            def request(self, method, url, **kwargs):
                self.request_options = kwargs
                if self.fail:
                    raise ssl.SSLError("synthetic_tls_validation_failure")
                return self.response
        payload = json.dumps(token()).encode()
        cases = [(302, {}, b"", False), (200, {"Content-Encoding": "gzip"}, b"", False),
                 (200, {}, b"x" * (BODY_LIMIT + 1), False), (200, {}, payload, True), (200, {}, payload, False)]
        for status, headers, body, fail in cases:
            response = ResponseFixture(status, headers, body)
            def factory(**kwargs):
                return SessionFixture(response, fail, **kwargs)
            with patch("symphonia_native_oauth_trial.provider.aiohttp.AsyncResolver", ResolverFixture), patch("symphonia_native_oauth_trial.provider.aiohttp.ClientSession", factory):
                if status == 200 and not headers and len(body) <= BODY_LIMIT and not fail:
                    self.assertEqual(payload, (await FixedHTTP().request("POST", TOKEN, deadline=time.time()+1200)).body)
                else:
                    with self.assertRaises(TrialError) as raised:
                        await FixedHTTP().request("POST", TOKEN, deadline=time.time()+1200)
                    self.assertEqual("uncertain", raised.exception.reason)
            self.assertTrue(sessions[-1].closed and resolvers[-1].closed)
            self.assertFalse(sessions[-1].options["trust_env"])
            self.assertFalse(sessions[-1].request_options["allow_redirects"])
            self.assertEqual("identity", sessions[-1].request_options["headers"]["Accept-Encoding"])
            self.assertIs(True, sessions[-1].options["connector"]._ssl)
        response = ResponseFixture(200, {}, b'{"account_id":"synthetic"}')
        with patch("symphonia_native_oauth_trial.provider.aiohttp.AsyncResolver", ResolverFixture), patch("symphonia_native_oauth_trial.provider.aiohttp.ClientSession", factory):
            observed = await FixedHTTP().request("GET", ME, deadline=time.time()+1200,
                headers={"Authorization": "Bearer synthetic", "Accept-Encoding": "gzip"})
        self.assertEqual(b'{"account_id":"synthetic"}', observed.body)
        self.assertEqual({"Authorization": "Bearer synthetic", "Accept-Encoding": "identity"},
                         sessions[-1].request_options["headers"])
        for method, url in (("GET", TOKEN), ("POST", ME), ("GET", ME+"/other"), ("GET", "http://127.0.0.1")):
            with self.subTest(url=url), self.assertRaises(TrialError):
                await FixedHTTP().request(method, url, deadline=time.time()+1200)

        arrived = asyncio.Event()
        class Blackhole(asyncio.DatagramProtocol):
            def datagram_received(self, data, address):
                arrived.set()
        loop = asyncio.get_running_loop()
        udp, _ = await loop.create_datagram_endpoint(Blackhole, local_addr=("127.0.0.1", 0))
        class TrackedResolver(aiohttp.AsyncResolver):
            finished = closed = False
            async def resolve(self, *args, **kwargs):
                try:
                    return await super().resolve(*args, **kwargs)
                finally:
                    self.finished = True
            async def close(self):
                await super().close()
                self.closed = True
        resolver = TrackedResolver(nameservers=["127.0.0.1"], udp_port=udp.get_extra_info("sockname")[1], timeout=60, tries=1)
        debug = loop.get_debug()
        loop.set_debug(False)
        task = None
        try:
            with patch("symphonia_native_oauth_trial.provider.aiohttp.AsyncResolver", lambda: resolver), patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:9"}):
                task = asyncio.create_task(FixedHTTP().request("POST", TOKEN, deadline=time.time()+1200))
                await asyncio.wait_for(arrived.wait(), 1)
                original_time = loop.time
                # DNS arrival proves the request already entered its own 10s
                # deadline. The outer 20s bound is only a longer safety net.
                # Advance the scheduler, not wall time or a real ten-second wait.
                with patch.object(loop, "time", lambda: original_time()+11):
                    with self.assertRaises(TrialError) as raised:
                        await asyncio.wait_for(task, 20)
                    self.assertEqual("uncertain", raised.exception.reason)
            self.assertTrue(task.done() and resolver.finished and resolver.closed)
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await resolver.close()
            udp.close()
            loop.set_debug(debug)


class NativeTrialPrivateTLSTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from tests.test_native_oauth_trial_state import FakeProvider
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        state = root / "app"
        state.mkdir(mode=0o700)
        self.server = compose(state, FakeProvider(), fresh=True)
        self.keys = CoreKeys(root / "core")
        self.actor = "synthetic-admin"
        meta = self.server.state.meta()
        self.csr = self.keys.create_csr(meta["installation"], self.actor)
        self.deadline = meta["deadline"]
        self.listener = await asyncio.start_server(self.server.private_stream, "127.0.0.1", 0,
            ssl=self.server.authority.context(), ssl_handshake_timeout=3, ssl_shutdown_timeout=0.5)
        self.port = self.listener.sockets[0].getsockname()[1]
        loop = asyncio.get_running_loop()
        original = loop.sock_connect
        self.original_connect = original
        async def local_connect(connection, address):
            self.assertEqual(("127.0.0.1", 8098), address)
            return await original(connection, ("127.0.0.1", self.port))
        class LocalResolver:
            async def resolve(resolver, host, port, family):
                if host != "local-symphonia-native-oauth-trial" or port != 8098:
                    raise AssertionError("unexpected_private_destination")
                return [{"host": "127.0.0.1"}]
            async def close(resolver):
                pass
        self.route = patch.object(loop, "sock_connect", local_connect)
        self.dns = patch.object(core_bridge.aiohttp, "AsyncResolver", LocalResolver)
        self.route.start(); self.dns.start()

    async def asyncTearDown(self):
        self.route.stop(); self.dns.stop()
        self.listener.close()
        await self.listener.wait_closed()
        await self.server.close_connections()
        self.server.state.close()
        self.directory.cleanup()

    def enrollment(self):
        return {"version": 1, "op": "pair.enroll", "actor": self.actor,
                "challenge": self.server.challenge, "csr": self.csr}

    def bridge(self, pin=None):
        return core_bridge.Bridge("local_symphonia_native_oauth_trial", pin or self.server.authority.pin,
                                  self.deadline, self.keys)

    async def test_adapter_C03_real_tls_checks_pin_before_bootstrap_and_requires_paired_identity(self):
        with self.assertRaises(core_bridge.BridgeError) as raised:
            await self.bridge("0" * 64).call(self.enrollment(), paired=False)
        self.assertEqual("tls_identity", raised.exception.reason)
        self.assertFalse(self.server.state.meta()["bootstrap_used"])
        good = self.bridge()
        original = self.server.state.meta()
        challenge = self.server.challenge
        for failure in (OSError("synthetic CA read failure"), TrialError("locked")):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(self.server.authority, "issue_request", side_effect=failure):
                    with self.assertRaises(core_bridge.BridgeError):
                        await good.call(self.enrollment(), paired=False)
                self.assertEqual(original, self.server.state.meta())
                self.assertEqual(challenge, self.server.trial.challenge)
                self.assertFalse(self.server.state.db.in_transaction)
        self.server.state.db.set_authorizer(lambda action, operation, *_:
            sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and operation == "COMMIT" else sqlite3.SQLITE_OK)
        try:
            with patch.object(self.server.authority, "issue_request", wraps=self.server.authority.issue_request) as issued:
                with self.assertRaises(core_bridge.BridgeError):
                    await good.call(self.enrollment(), paired=False)
                self.assertEqual(1, issued.call_count)
            self.assertEqual(original, self.server.state.meta())
            self.assertEqual(challenge, self.server.trial.challenge)
            self.assertFalse(self.server.state.db.in_transaction)
        finally:
            self.server.state.db.set_authorizer(None)
        # Reopen the real files after signing failure: no new identity, challenge,
        # bootstrap window or deadline is created, and valid enrollment still works.
        self.listener.close()
        await self.listener.wait_closed()
        await self.server.close_connections()
        state_path = self.server.state.path
        provider = self.server.trial.provider
        self.server.state.close()
        self.server = compose(state_path.parent, provider)
        self.assertEqual(original, self.server.state.meta())
        self.assertEqual(challenge, self.server.challenge)
        self.listener = await asyncio.start_server(self.server.private_stream, "127.0.0.1", 0,
            ssl=self.server.authority.context(), ssl_handshake_timeout=3, ssl_shutdown_timeout=0.5)
        self.port = self.listener.sockets[0].getsockname()[1]
        result = await good.call(self.enrollment(), paired=False)
        self.keys.accept(result["ca"], result["certificate"], installation=result["installation"],
                         pair_id=result["pair_id"], deadline=result["deadline"], server_der=good.server_der)
        self.assertEqual("paired", (await good.call({"version": 1, "op": "status", "pair_id": result["pair_id"]}))["phase"])
        self.assertTrue(self.server.state.meta()["bootstrap_used"])
        with self.assertRaises(core_bridge.BridgeError):
            await good.call(self.enrollment(), paired=False)
        with self.assertRaises(core_bridge.BridgeError):
            await good.call({"version": 1, "op": "status", "pair_id": "wrong-pair"})
        with self.assertRaises(core_bridge.BridgeError):
            await good.call({"version": 1, "op": "pair.enroll", "actor": self.actor,
                             "challenge": "synthetic", "csr": self.csr})
        with self.assertRaises(core_bridge.BridgeError):
            await good.call({"version": 1, "op": "unknown.operation"})
        with patch.object(self.server, "process", AsyncMock(return_value=[])):
            with self.assertRaises(core_bridge.BridgeError):
                await good.call({"version": 1, "op": "hello"})
        with patch.object(core_bridge.aiohttp.AsyncResolver, "resolve", AsyncMock(return_value=[])):
            with self.assertRaises(core_bridge.BridgeError):
                await good.call({"version": 1, "op": "hello"})
        with self.assertRaises(core_bridge.BridgeError):
            await core_bridge.Bridge("local_symphonia_native_oauth_trial", self.server.authority.pin, 1, self.keys).call({"version": 1, "op": "hello"})
        with self.assertRaises(core_bridge.BridgeError):
            await good.call({"version": 1, "op": "hello", "oversized": "x" * 16384})

        async def raw(request, authenticated=True):
            connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            connection.setblocking(False)
            await self.original_connect(connection, ("127.0.0.1", self.port))
            context = self.keys.context() if authenticated else ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if not authenticated:
                context.check_hostname = False; context.verify_mode = ssl.CERT_NONE
            reader, writer = await asyncio.open_connection(sock=connection, ssl=context,
                server_hostname="local-symphonia-native-oauth-trial", ssl_shutdown_timeout=.5)
            try:
                writer.write(request); await writer.drain()
                return await asyncio.wait_for(reader.read(), 4)
            finally:
                writer.close(); await writer.wait_closed()
        prefix = b"POST /internal/ha-oauth/v1 HTTP/1.1\r\nContent-Type: application/json\r\n"
        variants = [b"GET /unexpected HTTP/1.1\r\n\r\n",
            prefix+b"Content-Type: application/json\r\nContent-Length: 2\r\n\r\n{}",
            prefix+b"Content-Length: 0\r\n\r\n",
            prefix+b"Content-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n{}",
            prefix+b"Content-Length: 2\r\n\r\n[]",
            b"POST /internal/ha-oauth/v1 HTTP/1.1\r\nMalformed\r\n\r\n"]
        for value in variants:
            with self.subTest(framing=value[:60]):
                self.assertIn(b'"ok":false', await raw(value))
        # No body is sent: the peer certificate must be checked first.
        self.assertIn(b"HTTP/1.1 403", await raw(prefix+b"Content-Length: 100\r\n\r\n", authenticated=False))
        meta = self.server.state.meta()
        self.assertEqual({name: meta[name] for name in ("installation", "deadline")},
                         await good.call({"version": 1, "op": "hello"}))
        bound = Binding(meta["installation"], meta["pair_id"], meta["actor"], "flow", "attempt",
                        0, 0, "spotify", "public-client", PROFILE, REDIRECT, meta["deadline"])
        await good.call({"version": 1, "op": "attempt.start", "binding": bound.wire(), "verifier": "v" * 64})
        await good.call({"version": 1, "op": "attempt.stage", "binding": bound.wire(), "code": "synthetic-code"})
        self.server.trial.provider.gate = asyncio.Event()
        completion = asyncio.create_task(good.call({"version": 1, "op": "attempt.complete", "binding": bound.wire()}))
        await asyncio.wait_for(self.server.trial.provider.entered.wait(), 1)
        await self.server.close_connections()
        with self.assertRaises(core_bridge.BridgeError):
            await completion
        self.assertEqual("uncertain", self.server.state.status(time.time())["phase"])

    async def test_adapter_C04_csr_and_issued_certificate_bind_key_installation_purpose_and_deadline(self):
        authority = self.server.authority
        public = authority.csr(self.csr, self.actor)
        from symphonia_native_oauth_trial.policy import TrialError
        for csr, actor in ((self.csr, "other-admin"), ("invalid-csr", self.actor)):
            with self.subTest(actor=actor), self.assertRaises(TrialError):
                authority.csr(csr, actor)
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        wrong = authority.issue(ec.generate_private_key(ec.SECP256R1()).public_key(), "b" * 32,
                                self.server.state.meta()["started"])
        server_der = authority.server.public_bytes(serialization.Encoding.DER)
        with self.assertRaises(KeyUnavailable):
            self.keys.accept(authority.ca_pem, wrong, installation=authority.installation,
                             pair_id="b" * 32, deadline=self.deadline, server_der=server_der)
        self.assertFalse((self.keys.root / "ca.crt").exists())
        certificate = authority.issue(public, "b" * 32, self.server.state.meta()["started"])
        for installation, deadline in (("foreign-installation", self.deadline), (authority.installation, self.deadline + 1)):
            with self.subTest(installation=installation), self.assertRaises(KeyUnavailable):
                self.keys.accept(authority.ca_pem, certificate, installation=installation,
                                 pair_id="b" * 32, deadline=deadline, server_der=server_der)
        self.keys.accept(authority.ca_pem, certificate, installation=authority.installation,
                         pair_id="b" * 32, deadline=self.deadline, server_der=server_der)
        self.assertEqual(3, len(self.keys.hashes()))
        self.assertEqual(ssl.TLSVersion.TLSv1_3, self.keys.context().minimum_version)
        original = self.keys.hashes()
        with self.assertRaises(KeyUnavailable):
            self.keys.create_csr(authority.installation, self.actor)
        self.assertEqual(original, self.keys.hashes())
        with self.assertRaises(KeyUnavailable):
            with self.keys.descriptor("../core.key"):
                pass
        self.keys.root.chmod(0o755)
        try:
            with self.assertRaises(KeyUnavailable):
                self.keys.read("core.key")
            with self.assertRaises(KeyUnavailable):
                self.keys._create("extra.key", b"refused")
        finally:
            self.keys.root.chmod(0o700)
        with patch("custom_components.symphonia_native_oauth_trial.keys.os.read", return_value=b""):
            with self.assertRaises(KeyUnavailable):
                self.keys.read("core.key")
        ca_file = self.keys.root / "ca.crt"
        ca_raw = ca_file.read_bytes()
        ca_file.write_bytes(b"invalid-ca")
        with self.assertRaises(KeyUnavailable):
            self.keys.context()
        ca_file.write_bytes(ca_raw)
        with self.assertRaises(KeyUnavailable):
            self.keys.accept("invalid", certificate, installation=authority.installation,
                             pair_id="b" * 32, deadline=self.deadline, server_der=server_der)
        with self.assertRaises(KeyUnavailable):
            self.keys.remove_owned({**original, "core.key": "0" * 64})
        (self.keys.root / "unowned").write_text("preserve")
        with self.assertRaises(KeyUnavailable):
            self.keys.remove_owned(original)
        self.assertEqual(original, self.keys.hashes())
        partial = CoreKeys(self.keys.root.parent / "partial-core")
        partial.root.mkdir(mode=0o700)
        with patch("custom_components.symphonia_native_oauth_trial.keys.os.write", return_value=0):
            with self.assertRaises(KeyUnavailable):
                partial._create("core.key", b"partial")
        self.assertTrue((partial.root / "core.key").exists())


class NativeTrialCryptoTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name) / "keys"
        self.root.mkdir(mode=0o700)
        with PrivateFiles(self.root) as files:
            files.create("wrapping.key", os.urandom(32))
        self.vault = Vault(self.root)

    def tearDown(self):
        self.directory.cleanup()

    def test_adapter_C11_actual_aead_rejects_every_binding_and_ciphertext_change(self):
        original = binding()
        grant = Grant("private-access-canary", "private-refresh-canary", 2000)
        sealed = self.vault.seal(original, grant)
        self.assertEqual(grant, self.vault.open(original, sealed))
        self.assertNotIn(b"private-access-canary", sealed)
        self.assertNotEqual(sealed, self.vault.seal(original, grant))
        for name, value in original.wire().items():
            altered = replace(original, **{name: value + 1 if type(value) is int else value + "x"})
            with self.subTest(field=name), self.assertRaises(TrialError):
                self.vault.open(altered, sealed)
        for value in (sealed[:-1], bytes([sealed[0] ^ 1]) + sealed[1:], b"short"):
            with self.subTest(size=len(value)), self.assertRaises(TrialError):
                self.vault.open(original, value)

    def test_adapter_C12_missing_wrong_or_unsafe_existing_keys_lock_without_rekey(self):
        sealed = self.vault.seal(binding(), Grant("access", "refresh", 2000))
        key = self.root / "wrapping.key"
        for raw in (b"wrong", os.urandom(32)):
            key.write_bytes(raw)
            with self.subTest(size=len(raw)), self.assertRaises(TrialError):
                self.vault.open(binding(), sealed)
            self.assertEqual(raw, key.read_bytes())
        key.unlink()
        with self.assertRaises(TrialError):
            self.vault.open(binding(), sealed)
        self.assertFalse(key.exists())
        target = self.root / "other.key"
        target.write_bytes(os.urandom(32)); target.chmod(0o600)
        key.symlink_to(target)
        with self.assertRaises(TrialError):
            self.vault.open(binding(), sealed)
        self.assertTrue(key.is_symlink())
        key.unlink(); os.link(target, key)
        with self.assertRaises(TrialError):
            self.vault.open(binding(), sealed)
        key.unlink(); target.rename(key)
        key.chmod(0o644)
        with self.assertRaises(TrialError):
            self.vault.open(binding(), sealed)
        self.assertEqual(0o644, key.stat().st_mode & 0o777)
        key.chmod(0o600)
        with PrivateFiles(self.root) as files:
            for name in ("../wrapping.key", "/etc/passwd", "x..y", None):
                with self.subTest(name=name), self.assertRaises(TrialError):
                    files.read(name)
            for content in (b"", b"x" * 16385, "not-bytes"):
                with self.subTest(size=len(content)), self.assertRaises(TrialError):
                    files.create("invalid.key", content)
            with self.assertRaises(TrialError):
                files.create("wrapping.key", b"replacement")
            with self.assertRaises(TrialError):
                with files.descriptor("missing.key"):
                    pass
            with patch("symphonia_native_oauth_trial.keys.os.read", return_value=b""):
                with self.assertRaises(TrialError):
                    files.read("wrapping.key")
        self.root.chmod(0o755)
        with self.assertRaises(TrialError):
            PrivateFiles(self.root)
        self.root.chmod(0o700)
