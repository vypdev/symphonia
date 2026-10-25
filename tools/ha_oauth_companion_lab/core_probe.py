"""Isolated real-Core HTTP experiment; run inside the disposable Core image.

No provider requests, real user credentials, installed production integration
or existing Core configuration are used. Only a bounded boolean receipt exits.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import tempfile
from urllib.parse import parse_qs, urlsplit


DOMAIN = "symphonia_oauth_lab_probe"
FLOW_SOURCE = '''"""Synthetic native flow, never a provider implementation."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import http
from homeassistant.components.http import KEY_HASS_USER
from homeassistant.helpers import config_entry_oauth2_flow as oauth

DOMAIN = "symphonia_oauth_lab_probe"

def actor():
    request = http.current_request.get()
    user = request.get(KEY_HASS_USER) if request is not None else None
    return user.id if user and user.is_active and user.is_admin else None

class NoProvider(oauth.LocalOAuth2ImplementationWithPkce):
    async def async_resolve_external_data(self, data):
        raise AssertionError("provider_exchange_forbidden_in_probe")

class ProbeFlow(oauth.AbstractOAuth2FlowHandler, domain=DOMAIN):
    DOMAIN = DOMAIN
    VERSION = 1
    owner = None
    @property
    def logger(self):
        return logging.getLogger(DOMAIN)

    async def async_step_user(self, user_input=None):
        current = actor()
        if current is None:
            return self.async_abort(reason="missing_native_actor")
        if user_input is None:
            self.owner = current
            return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
        if current != self.owner:
            return self.async_abort(reason="wrong_actor")
        return self.async_create_entry(title="Disposable OAuth pair", data={"lab_only": True})

    async def async_step_reconfigure(self, user_input=None):
        current = actor()
        if current is None:
            return self.async_abort(reason="missing_native_actor")
        self.owner = current
        return await self.begin()

    async def async_step_reauth(self, entry_data):
        # A background reauth start has no fresh user: capture at native POST.
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({}))

    async def async_step_reauth_confirm(self, user_input=None):
        current = actor()
        if current is None:
            return self.async_abort(reason="missing_native_actor")
        self.owner = current
        return await self.begin()

    async def begin(self):
        self.flow_impl = NoProvider(self.hass, DOMAIN, "a" * 32,
            "https://oauth.example.invalid/authorize", "https://oauth.example.invalid/token")
        self.hass.data.setdefault(DOMAIN, {})[self.flow_id] = {
            "owner": self.owner, "verifier": self.flow_impl.code_verifier,
            "completed": False, "callback_has_no_actor": None}
        return await self.async_step_auth()

    async def async_step_auth(self, user_input=None):
        if user_input is not None:
            self.hass.data[DOMAIN][self.flow_id]["callback_has_no_actor"] = actor() is None
        return await super().async_step_auth(user_input)

    async def async_step_creation(self, user_input=None):
        current = actor()
        state = self.hass.data[DOMAIN][self.flow_id]
        errors = {}
        if current is None:
            errors["base"] = "missing_native_actor"
        elif current != self.owner:
            errors["base"] = "wrong_actor"
        elif user_input and user_input.get("confirm") is True:
            state["completed"] = True
            self.external_data.clear()
            self.flow_impl.code_verifier = ""
            state.pop("verifier", None)
            entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
            return self.async_update_reload_and_abort(entry,
                data_updates={"lab_only": True, "safe_result": "synthetic_staged_return_confirmed"},
                reason="probe_completed")
        return self.async_show_form(step_id="creation",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}), errors=errors)
'''


async def run_probe():
    # A research Core instance must not discover the surrounding Supervisor.
    # The recommended invocation also has --network none and no mounted config.
    os.environ.clear()
    os.environ["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    from aiohttp import ClientSession
    from homeassistant import bootstrap, config_entries, loader
    from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
    from homeassistant.const import __version__
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.storage import Store

    logging.getLogger().setLevel(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix="symphonia-core-http-probe-") as directory:
        root = Path(directory)
        fixture = root / "custom_components" / DOMAIN
        fixture.mkdir(parents=True)
        (fixture / "manifest.json").write_text(json.dumps({"domain": DOMAIN,
            "name": "Disposable OAuth probe", "version": "0.0.0-lab",
            "config_flow": True, "documentation": "https://example.invalid/",
            "codeowners": [], "requirements": [], "iot_class": "local_push"}))
        (fixture / "__init__.py").write_text(
            "async def async_setup_entry(hass, entry):\n    return True\n"
            "async def async_unload_entry(hass, entry):\n    return True\n")
        (fixture / "config_flow.py").write_text(FLOW_SOURCE)
        with socket.socket() as selection:
            selection.bind(("127.0.0.1", 0))
            port = selection.getsockname()[1]
        hass = HomeAssistant(directory)
        loader.async_setup(hass)
        hass.config.skip_pip = True
        receipt = {"mode": "isolated_real_core_http", "core": __version__,
            "real_spotify": "not_run", "existing_core_config_used": False}
        secret_canaries = []
        try:
            result = await bootstrap.async_from_config_dict({
                "http": {"server_host": "127.0.0.1", "server_port": port},
                "api": {}, "config": {},
            }, hass)
            assert result is hass, "bootstrap_failed"
            await hass.async_start()
            # Core makes its first user owner; use a distinct fixture owner so
            # deactivation tests exercise an ordinary administrator.
            await hass.auth.async_create_user("Probe Owner", group_ids=[GROUP_ID_ADMIN])
            users = []
            credentials = []
            for name, group in (("Probe Admin A", GROUP_ID_ADMIN),
                                ("Probe Admin B", GROUP_ID_ADMIN),
                                ("Probe Non-admin", GROUP_ID_USER)):
                user = await hass.auth.async_create_user(name, group_ids=[group])
                refresh = await hass.auth.async_create_refresh_token(user,
                    client_id="https://probe.example.invalid")
                users.append(user)
                credentials.append((hass.auth.async_create_access_token(refresh), refresh))
            base = f"http://127.0.0.1:{port}"
            index = "/api/config/config_entries/flow"
            async with ClientSession() as client:
                async def request(method, path, who=None, data=None):
                    headers = {"HA-Frontend-Base": base}
                    if who is not None:
                        headers["Authorization"] = "Bearer " + credentials[who][0]
                    async with client.request(method, base + path, headers=headers,
                                              json=data, allow_redirects=False) as response:
                        raw = await response.read()
                        return response.status, json.loads(raw) if response.content_type == "application/json" else None

                status, _ = await request("POST", index, data={"handler": DOMAIN})
                receipt["unauthenticated_native_begin_status"] = status
                status, denied = await request("POST", index, 2, {"handler": DOMAIN})
                receipt["non_admin_native_begin_status"] = status
                receipt["non_admin_native_begin_rejected"] = status in (401, 403) or (
                    (denied or {}).get("type") == "abort" and (denied or {}).get("reason") == "missing_native_actor")
                status, flow = await request("POST", index, 0, {"handler": DOMAIN})
                assert status == 200 and flow["type"] == "form", "native_pair_flow_failed"
                status, paired = await request("POST", index + "/" + flow["flow_id"], 0, {})
                assert status == 200 and paired["type"] == "create_entry", "native_pair_entry_failed"
                entry_id = paired["result"]["entry_id"]
                entry = hass.config_entries.async_get_entry(entry_id)

                async def begin():
                    status, flow = await request("POST", index, 0, {"handler": DOMAIN, "entry_id": entry_id})
                    assert status == 200 and flow["type"] == "external", "native_reconfigure_failed"
                    query = parse_qs(urlsplit(flow["url"]).query)
                    return flow["flow_id"], query

                first, query = await begin()
                second, query2 = await begin()
                secret_canaries.extend(hass.data[DOMAIN][flow]["verifier"].encode()
                                       for flow in (first, second))
                receipt["reconfigure_uses_main_config_flow"] = True
                receipt["pkce_s256"] = query["code_challenge_method"] == ["S256"]
                receipt["separate_pkce_per_attempt"] = query["code_challenge"] != query2["code_challenge"]
                callback = "/auth/external/callback"
                # Real Core callback validation; no browser or provider requests.
                status, _ = await request("GET", callback + "?state=invalid&code=synthetic")
                receipt["wrong_state_callback_status"] = status
                from urllib.parse import urlencode
                callback_code = "synthetic-code-" + secrets.token_hex(8)
                secret_canaries.append(callback_code.encode())
                status, _ = await request("GET", callback + "?" + urlencode({
                    "state": query["state"][0], "code": callback_code}))
                receipt["valid_callback_status"] = status
                receipt["callback_without_admin_actor"] = hass.data[DOMAIN][first]["callback_has_no_actor"]
                receipt["callback_did_not_complete"] = not hass.data[DOMAIN][first]["completed"]
                status, shown = await request("POST", index + "/" + first, 0, {})
                assert status == 200 and shown["step_id"] == "creation", "native_confirmation_not_shown"
                status, wrong = await request("POST", index + "/" + first, 1, {"confirm": True})
                receipt["different_admin_rejected_by_fresh_actor"] = (
                    status == 200 and wrong.get("errors", {}).get("base") == "wrong_actor"
                    and not hass.data[DOMAIN][first]["completed"])
                status, denied = await request("POST", index + "/" + first, 2, {"confirm": True})
                receipt["non_admin_confirm_status"] = status
                receipt["non_admin_confirm_rejected"] = status in (401, 403) or (
                    (denied or {}).get("errors", {}).get("base") == "missing_native_actor"
                    and not hass.data[DOMAIN][first]["completed"])
                status, done = await request("POST", index + "/" + first, 0, {"confirm": True})
                receipt["initiating_admin_fresh_confirmation"] = (
                    status == 200 and done.get("reason") == "probe_completed"
                    and hass.data[DOMAIN][first]["completed"])
                receipt["safe_config_entry_only"] = entry.data == {
                    "lab_only": True, "safe_result": "synthetic_staged_return_confirmed"}
                receipt["no_ha_token_entry_or_refresh_session"] = "token" not in entry.data

                # Actual framework denial of a disabled user and revoked login.
                await hass.auth.async_update_user(users[0], is_active=False)
                status, _ = await request("POST", index + "/" + second, 0, {})
                receipt["disabled_user_native_status"] = status
                await hass.auth.async_update_user(users[0], is_active=True)
                hass.auth.async_remove_refresh_token(credentials[0][1])
                status, _ = await request("POST", index + "/" + second, 0, {})
                receipt["revoked_login_native_status"] = status

                # Background reauth must wait for an authenticated native POST.
                hass.config_entries.flow.async_abort(second)
                entry.async_start_reauth(hass)
                await hass.async_block_till_done()
                pending = [f for f in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
                           if f["context"]["source"] == config_entries.SOURCE_REAUTH]
                assert len(pending) == 1, "reauth_flow_missing"
                status, restarted = await request("POST", index + "/" + pending[0]["flow_id"], 1, {})
                receipt["reauth_uses_fresh_native_request"] = status == 200 and restarted["type"] == "external"

            canary = "SYNTHETIC-PAIR-KEY-" + secrets.token_hex(24)
            store = Store(hass, 1, "symphonia_oauth_lab_plaintext_control", private=True)
            await store.async_save({"test_key": canary})
            stored = root / ".storage" / "symphonia_oauth_lab_plaintext_control"
            receipt["private_store_mode_0600"] = stored.stat().st_mode & 0o777 == 0o600
            receipt["private_store_is_plaintext"] = canary in stored.read_text()
            receipt["native_provider_exchange_performed"] = False
            assert receipt["unauthenticated_native_begin_status"] == 401
            assert receipt["non_admin_native_begin_rejected"]
            assert receipt["non_admin_confirm_rejected"]
            assert receipt["valid_callback_status"] == 200
            assert receipt["different_admin_rejected_by_fresh_actor"]
            assert receipt["initiating_admin_fresh_confirmation"]
            assert receipt["disabled_user_native_status"] in (401, 403)
            assert receipt["revoked_login_native_status"] == 401
            return receipt
        except Exception:
            print(json.dumps({"partial_receipt": receipt}, sort_keys=True))
            raise
        finally:
            await hass.async_stop()
            if secret_canaries:
                stored = [path.read_bytes() for path in root.rglob("*")
                          if path.is_file() and path.stat().st_size < 4 * 1024 * 1024]
                receipt["oauth_code_and_verifiers_absent_from_saved_config"] = not any(
                    canary in body for canary in secret_canaries for body in stored)
                assert receipt["oauth_code_and_verifiers_absent_from_saved_config"], "oauth_canary_persisted"


if __name__ == "__main__":
    try:
        print(json.dumps(asyncio.run(run_probe()), sort_keys=True))
    except Exception as error:
        # No raw request, token, callback or exception args leave the fixture.
        import traceback
        print(json.dumps({"probe": "failed", "exception_type": type(error).__name__,
            "location": [{"function": frame.name, "line": frame.lineno}
                         for frame in traceback.extract_tb(error.__traceback__)[-3:]]}))
        raise SystemExit(1) from None
