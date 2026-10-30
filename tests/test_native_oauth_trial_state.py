"""Twelve state cases use real SQLite; provider and crypto ports are explicit fakes."""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from symphonia_native_oauth_trial.application import Grant, Trial
from symphonia_native_oauth_trial.policy import Binding, PROFILE, REDIRECT, TrialError
from symphonia_native_oauth_trial.store import Store


class FakeProvider:
    def __init__(self):
        self.exchanges = self.refreshes = self.accounts = 0
        self.gate = None
        self.entered = asyncio.Event()
        self.fail = None

    async def _wait(self):
        self.entered.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise self.fail

    async def exchange(self, binding, code, verifier):
        self.exchanges += 1
        await self._wait()
        return Grant("synthetic-access-canary", "synthetic-refresh-canary", 1800)

    async def refresh(self, binding, grant):
        self.refreshes += 1
        await self._wait()
        return Grant("synthetic-new-access", grant.refresh, 1900)

    async def account(self, binding, grant):
        self.accounts += 1
        return "a" * 64


class FakeCipher:
    """Opaque memory lookup, expressly NOT encryption/AEAD evidence."""
    def __init__(self):
        self.values = {}

    def seal(self, binding, grant):
        blob = b"fake-sealed-" + str(len(self.values)).encode()
        self.values[blob] = grant
        return blob

    def open(self, binding, sealed):
        return self.values[sealed]


class NativeTrialStateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "trial.sqlite"
        self.now = 1000
        self.store = Store.provision(self.path, "installation", 1000)
        meta = self.store.enroll("admin", "a" * 64, self.now)
        self.binding = Binding("installation", meta["pair_id"], "admin", "consent-flow", "attempt", 0, 0,
                               "spotify", "opaque-client", PROFILE, REDIRECT, 2200)
        self.provider, self.cipher = FakeProvider(), FakeCipher()
        self.app = Trial(self.store, self.provider, self.cipher, lambda: self.now)

    async def asyncTearDown(self):
        self.store.close()
        self.directory.cleanup()

    def stage(self):
        self.app.start(self.binding, "v" * 64)
        self.app.stage(self.binding, "synthetic-code-canary")

    def restart(self):
        self.store.close()
        self.store = Store(self.path)
        self.app = Trial(self.store, self.provider, self.cipher, lambda: self.now)

    async def test_state_C01_callback_only_stages(self):
        self.stage()
        self.assertEqual("staged", self.store.status(self.now)["phase"])
        self.assertEqual(0, self.provider.exchanges)
        raw = self.path.read_bytes()
        self.assertNotIn(b"synthetic-code-canary", raw)
        self.assertNotIn(b"v" * 64, raw)

    async def test_state_C02_denial_is_terminal_without_grant(self):
        self.app.start(self.binding, "v" * 64)
        self.app.terminal(self.binding, "denied")
        self.assertEqual("denied", self.store.status(self.now)["phase"])
        self.assertFalse(self.app.transient)
        with self.assertRaises(TrialError):
            await self.app.complete(self.binding)
        self.assertEqual(0, self.provider.exchanges)

    async def test_state_C03_cancel_and_expiry_refuse_late_work(self):
        self.stage()
        self.app.terminal(self.binding, "cancelled")
        with self.assertRaises(TrialError):
            await self.app.complete(self.binding)
        self.now = 2200
        self.assertEqual("expired", self.store.status(self.now)["phase"])
        with self.assertRaises(TrialError):
            self.app.stage(self.binding, "late-code")
        self.assertEqual(0, self.provider.exchanges)

    async def test_state_C04_first_staged_code_and_binding_are_immutable(self):
        with self.assertRaises(TrialError):
            self.store.grant(self.binding, self.now)
        with self.assertRaises(TrialError):
            self.store.enroll("admin", "invalid-peer", self.now)
        self.app.start(self.binding, "v" * 64)
        with self.assertRaises(TrialError):
            self.store.validate_staged(self.binding, self.now)
        self.app.stage(self.binding, "synthetic-code-canary")
        self.assertEqual("staged", self.app.stage(self.binding, "synthetic-code-canary")["phase"])
        for binding, code in ((self.binding, "different-code"),
                              (replace(self.binding, flow="stale-flow"), "synthetic-code-canary")):
            with self.subTest(flow=binding.flow), self.assertRaises(TrialError):
                self.app.stage(binding, code)
        self.assertEqual(0, self.provider.exchanges)
        with self.assertRaises(TrialError):
            self.store.terminal(self.binding, self.now, "unsupported")
        with self.assertRaises(TrialError):
            self.store.commit(self.binding, "wrong-owner", b"", "account", self.now)

    async def test_state_C05_changed_or_absent_actor_and_epoch_cannot_complete(self):
        self.stage()
        for binding in (replace(self.binding, actor="other-admin"), replace(self.binding, actor=""),
                        replace(self.binding, pair_epoch=1)):
            with self.subTest(binding=binding), self.assertRaises(TrialError):
                await self.app.complete(binding)
        self.assertEqual(0, self.provider.exchanges)
        await self.app.complete(self.binding)
        self.assertEqual(1, self.provider.exchanges)

    async def test_state_C06_concurrent_completion_has_one_durable_owner(self):
        self.stage()
        self.provider.gate = asyncio.Event()
        first = asyncio.create_task(self.app.complete(self.binding))
        await asyncio.wait_for(self.provider.entered.wait(), 1)
        self.assertEqual("exchanging", (await self.app.complete(self.binding))["phase"])
        row = self.store.db.execute("SELECT phase,owner FROM attempt").fetchone()
        self.assertEqual("exchanging", row[0])
        self.assertTrue(row[1])
        self.assertEqual(1, self.provider.exchanges)
        self.provider.gate.set()
        self.assertEqual("active", (await first)["phase"])

    async def test_state_C07_lost_reply_and_repeated_completion_use_safe_status(self):
        self.stage()
        await self.app.complete(self.binding)  # reply intentionally discarded
        for _ in range(2):
            self.assertEqual("active", (await self.app.complete(self.binding))["phase"])
        self.assertEqual(1, self.provider.exchanges)

    async def test_state_C08_unknown_exchange_is_not_replayed_after_restart(self):
        self.stage()
        self.provider.fail = RuntimeError("synthetic_lost_response")
        with self.assertRaises(RuntimeError):
            await self.app.complete(self.binding)
        self.restart()
        self.assertEqual("uncertain", self.store.status(self.now)["phase"])
        with self.assertRaises(TrialError):
            await self.app.complete(self.binding)
        self.assertEqual(1, self.provider.exchanges)

    async def test_state_C09_failed_ciphertext_transaction_never_activates_partial_grant(self):
        self.stage()
        def fail(point):
            if point == "ciphertext_staged":
                raise OSError("synthetic_transaction_fault")
        self.store.checkpoint = fail
        with self.assertRaises(OSError):
            await self.app.complete(self.binding)
        row = self.store.db.execute("SELECT phase,sealed,account FROM attempt").fetchone()
        self.assertEqual(("uncertain", None, None), tuple(row))
        self.assertEqual(1, self.provider.exchanges)

    async def test_state_C10_refresh_is_single_flight_and_only_once(self):
        self.stage()
        await self.app.complete(self.binding)
        self.provider.gate, self.provider.entered = asyncio.Event(), asyncio.Event()
        first = asyncio.create_task(self.app.refresh(self.binding, "new-native-flow"))
        await asyncio.wait_for(self.provider.entered.wait(), 1)
        self.assertEqual("refreshing", (await self.app.refresh(self.binding, "new-native-flow"))["phase"])
        self.provider.gate.set()
        self.assertEqual("verified", (await first)["phase"])
        self.assertEqual("verified", (await self.app.refresh(self.binding, "another-flow"))["phase"])
        self.assertEqual(1, self.provider.refreshes)

    async def test_state_C11_unknown_refresh_never_reuses_old_grant(self):
        self.stage()
        await self.app.complete(self.binding)
        self.provider.fail = RuntimeError("synthetic_refresh_response_lost")
        with self.assertRaises(RuntimeError):
            await self.app.refresh(self.binding, "new-native-flow")
        self.restart()
        with self.assertRaises(TrialError):
            await self.app.refresh(self.binding, "yet-another-flow")
        self.assertEqual(1, self.provider.refreshes)
        self.assertEqual("uncertain", self.store.status(self.now)["phase"])

    async def test_state_C12_retirement_fences_late_owner_before_more_provider_io(self):
        self.stage()
        self.provider.gate = asyncio.Event()
        task = asyncio.create_task(self.app.complete(self.binding))
        await asyncio.wait_for(self.provider.entered.wait(), 1)
        self.app.retire()
        self.provider.gate.set()
        with self.assertRaises(TrialError):
            await task
        self.assertEqual(0, self.provider.accounts)
        row = self.store.db.execute("SELECT phase,sealed FROM attempt").fetchone()
        self.assertEqual(("retired", None), tuple(row))
        self.assertEqual({"phase": "retired", "deadline": 2200}, self.store.status(self.now))
        self.restart()
        self.assertEqual("retired", self.store.status(self.now)["phase"])
        self.assertEqual("retired", self.store.status(2200)["phase"])
        self.assertEqual("locked", self.store.status(999)["phase"])
        with self.assertRaises(TrialError):
            self.store.grant(self.binding, self.now)
