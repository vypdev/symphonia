"""Native forms and staged Core callback; never creates provider token entries."""
import asyncio
from functools import partial
from pathlib import Path
import re
import secrets
import stat
import os

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import http
from homeassistant.components.http import KEY_HASS_USER
from homeassistant.helpers.config_entry_oauth2_flow import LocalOAuth2ImplementationWithPkce
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from .bridge import Bridge, BridgeError, REDIRECT, SCOPE, authorize, bootstrap, callback_input, native_action, mark_request, validate_reference, validated_actor
from .keys import CoreKeys, KeyUnavailable, spki
from . import record_runtime_cache

DOMAIN = "symphonia_native_oauth_trial"


def current_actor():
    request = http.current_request.get()
    return validated_actor(request, KEY_HASS_USER)


def key_parent(hass):
    path = Path(hass.config.path(".storage", DOMAIN))
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise KeyUnavailable
    return path


class NativeTrialFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        super().__init__()
        self.actor = None
        self.binding = None
        self.staged = False

    async def action(self, value):
        return await native_action(http.current_request.get(), current_actor(), self.actor, self.flow_id, value)

    def pair_form(self, error=None):
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("app_slug", default="local_symphonia_native_oauth_trial"): str,
            vol.Required("client_id"): str, vol.Required("bootstrap"): str,
            vol.Required("encrypted_core_backups", default=False): bool}),
            errors={"base": "trial_unavailable"} if error else {})

    async def async_step_user(self, user_input=None):
        from homeassistant.const import __version__
        import platform
        if __version__ != "2026.10.4" or platform.machine() not in {"aarch64", "arm64"}:
            return self.async_abort(reason="unsupported_core")
        actor = current_actor()
        if actor is None:
            return self.async_abort(reason="administrator_required")
        if user_input is None:
            self.actor = actor
            await self.hass.async_add_executor_job(record_runtime_cache)
            return self.pair_form()
        try:
            await self.action(user_input)
            client = user_input["client_id"]
            if (user_input.get("encrypted_core_backups") is not True or not isinstance(client, str)
                    or not 1 <= len(client) <= 256 or not client.strip()
                    or any(not 32 <= ord(c) <= 126 for c in client)):
                raise BridgeError("invalid_input")
            bundle = bootstrap(user_input["bootstrap"])
            parent = await self.hass.async_add_executor_job(key_parent, self.hass)
            keys = CoreKeys(parent / bundle["installation"])
            csr = await self.hass.async_add_executor_job(keys.create_csr, bundle["installation"], actor)
            bridge = Bridge(user_input["app_slug"], bundle["pin"], bundle["deadline"], keys)
            result = await bridge.call({"version": 1, "op": "pair.enroll", "actor": actor,
                                        "challenge": bundle["challenge"], "csr": csr}, paired=False)
            if (set(result) != {"installation", "pair_id", "pair_epoch", "credential_epoch", "actor", "deadline", "ca", "certificate"}
                    or result["installation"] != bundle["installation"] or result["deadline"] != bundle["deadline"]
                    or result["actor"] != actor or type(result["pair_epoch"]) is not int or result["pair_epoch"] != 0
                    or type(result["credential_epoch"]) is not int or result["credential_epoch"] != 0
                    or not isinstance(result["pair_id"], str) or re.fullmatch(r"[a-f0-9]{32}", result["pair_id"]) is None):
                raise BridgeError("rejected")
            await self.hass.async_add_executor_job(partial(keys.accept, result["ca"], result["certificate"],
                installation=bundle["installation"], pair_id=result["pair_id"], deadline=bundle["deadline"], server_der=bridge.server_der))
            await self.async_set_unique_id(bundle["installation"])
            self._abort_if_unique_id_configured()
            data = {name: result[name] for name in ("installation", "pair_id", "pair_epoch", "credential_epoch", "actor", "deadline")}
            data.update(schema=1, app_slug=user_input["app_slug"], client_id=client, pin=bundle["pin"])
            data["material_hashes"] = await self.hass.async_add_executor_job(keys.hashes)
            validate_reference(data)
            return self.async_create_entry(title="Symphonia OAuth Trial", data=data)
        except (BridgeError, KeyUnavailable, ValueError, KeyError, TypeError):
            return self.async_abort(reason="pairing_failed_retire_trial")

    def bridge(self):
        data = validate_reference(self.entry.data)
        return Bridge(data["app_slug"], data["pin"], data["deadline"],
                      CoreKeys(Path(self.hass.config.path(".storage", DOMAIN, data["installation"]))))

    def confirmation(self, step, error=False):
        return self.async_show_form(step_id=step, data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            description_placeholders={"scope": SCOPE, "deadline": str(self.entry.data["deadline"])}, errors={"base": "administrator_required"} if error else {})

    async def status(self):
        return await self.bridge().call({"version": 1, "op": "status", "pair_id": self.entry.data["pair_id"]})

    def operation_form(self, error=False):
        return self.async_show_form(step_id="reconfigure", data_schema=vol.Schema({
            vol.Required("operation"): SelectSelector(SelectSelectorConfig(options=self.operations,
                translation_key="trial_operation", mode=SelectSelectorMode.DROPDOWN))}),
            errors={"base": "administrator_required"} if error else {},
            description_placeholders={"deadline": str(self.entry.data["deadline"])})

    async def async_step_reconfigure(self, user_input=None):
        self.entry = self._get_reconfigure_entry()
        try:
            validate_reference(self.entry.data)
        except BridgeError:
            return self.async_abort(reason="trial_unavailable")
        self.actor = self.entry.data["actor"]
        current = current_actor()
        if current is None:
            return self.async_abort(reason="administrator_required")
        if self.entry.data.get("retired") is True:
            return self.async_abort(reason="retirement_key_cleanup_pending" if self.entry.data.get("key_cleanup_pending") else "trial_retired")
        if user_input is None:
            self.navigation_actor = current
            try:
                result = await self.status()
            except (BridgeError, KeyUnavailable, KeyError, TypeError):
                result = {"phase": "unavailable"}
            self.operations = []
            if current == self.actor and result.get("phase") == "paired":
                self.operations.append("connect")
            if current == self.actor and result.get("phase") == "active" and self.entry.data.get("binding"):
                self.operations.append("refresh")
            self.operations.append("retire")
            return self.operation_form()
        try:
            await native_action(http.current_request.get(), current, self.navigation_actor, self.flow_id, user_input)
            operation = user_input.get("operation")
            if operation not in self.operations:
                raise BridgeError("rejected")
            if operation == "refresh":
                self.binding = dict(self.entry.data["binding"])
            if operation == "retire":
                self.retirement_actor = current
            return self.confirmation(operation)
        except (BridgeError, KeyError, TypeError):
            return self.operation_form(error=True)

    async def async_step_connect(self, user_input=None):
        if not user_input or user_input.get("confirm") is not True:
            return self.confirmation("connect")
        verifier = None
        try:
            await self.action(user_input)
        except BridgeError:
            return self.confirmation("connect", error=True)
        try:
            lock = self.hass.data[DOMAIN].setdefault(self.entry.entry_id, asyncio.Lock())
            async with lock:
                if (await self.status()).get("phase") != "paired":
                    raise BridgeError("rejected")
                data = self.entry.data
                self.binding = {name: data[name] for name in ("installation", "pair_id", "pair_epoch", "credential_epoch", "actor", "client_id", "deadline")}
                self.binding.update(provider="spotify", profile="trial_read_private", redirect=REDIRECT,
                                    flow=self.flow_id, attempt=secrets.token_hex(16))
                self.url, verifier = await authorize(self.hass, self.flow_id, data["client_id"], LocalOAuth2ImplementationWithPkce)
                self.hass.config_entries.async_update_entry(self.entry, data={**data, "binding": self.binding})
                await self.bridge().call({"version": 1, "op": "attempt.start", "binding": self.binding, "verifier": verifier})
            return self.async_external_step(step_id="auth", url=self.url)
        except (BridgeError, KeyUnavailable, ValueError, KeyError, TypeError):
            return self.async_abort(reason="trial_unavailable")
        finally:
            verifier = None

    async def async_step_auth(self, user_input=None):
        if user_input is None:
            return self.async_external_step(step_id="auth", url=self.url)
        material = None
        try:
            request = http.current_request.get()
            mark_request(request, self.flow_id)
            operation, material = callback_input(request, self.flow_id, user_input)
            if operation == "cancel":
                await self.bridge().call({"version": 1, "op": "attempt.cancel", "binding": self.binding, "reason": "denied"})
                return self.async_abort(reason="consent_denied")
            try:
                result = await self.bridge().call({"version": 1, "op": "attempt.stage", "binding": self.binding, "code": material})
            except BridgeError:
                result = await self.status()  # Safe lookup; never exchange/replay code.
            if result.get("phase") != "staged":
                raise BridgeError("rejected")
            self.staged = True
            return self.async_external_step_done(next_step_id="confirm")
        except (BridgeError, KeyUnavailable, KeyError, TypeError):
            return self.async_abort(reason="trial_unavailable")
        finally:
            material = None

    async def async_step_confirm(self, user_input=None):
        if not user_input or user_input.get("confirm") is not True:
            return self.confirmation("confirm")
        try:
            await self.action(user_input)
        except BridgeError:
            return self.confirmation("confirm", error=True)
        try:
            if not self.staged:
                raise BridgeError("rejected")
            try:
                result = await self.bridge().call({"version": 1, "op": "attempt.complete", "binding": self.binding})
            except BridgeError:
                result = await self.status()
            return self.async_abort(reason="oauth_active" if result.get("phase") == "active" else "trial_unavailable")
        except (BridgeError, KeyUnavailable, KeyError, TypeError):
            return self.async_abort(reason="trial_unavailable")

    async def async_step_refresh(self, user_input=None):
        if not user_input or user_input.get("confirm") is not True:
            return self.confirmation("refresh")
        try:
            await self.action(user_input)
        except BridgeError:
            return self.confirmation("refresh", error=True)
        try:
            try:
                result = await self.bridge().call({"version": 1, "op": "grant.refresh", "binding": self.binding, "confirmation_flow": self.flow_id})
            except BridgeError:
                result = await self.status()
            return self.async_abort(reason="trial_verified" if result.get("phase") == "verified" else "trial_unavailable")
        except (BridgeError, KeyUnavailable, KeyError, TypeError):
            return self.async_abort(reason="trial_unavailable")


    async def async_step_retire(self, user_input=None):
        if not user_input or user_input.get("confirm") is not True:
            return self.confirmation("retire")
        try:
            await native_action(http.current_request.get(), current_actor(), self.retirement_actor, self.flow_id, user_input)
        except BridgeError:
            return self.confirmation("retire", error=True)
        try:
            data = validate_reference(self.entry.data)
            result = await self.bridge().call({"version": 1, "op": "pair.revoke", "pair_id": data["pair_id"]})
            if result.get("phase") not in ("expired", "retired"):
                raise BridgeError("rejected")
        except (BridgeError, KeyUnavailable):
            return self.async_abort(reason="retirement_unconfirmed")
        pending = False
        try:
            keys = CoreKeys(Path(self.hass.config.path(".storage", DOMAIN, data["installation"])))
            await self.hass.async_add_executor_job(keys.remove_owned, data["material_hashes"])
        except (KeyUnavailable, OSError):
            pending = True
        self.hass.config_entries.async_update_entry(self.entry, data={**data, "retired": True, "key_cleanup_pending": pending})
        return self.async_abort(reason="retirement_key_cleanup_pending" if pending else "trial_retired")
