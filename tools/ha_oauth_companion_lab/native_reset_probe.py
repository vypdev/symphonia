"""Real Core HTTP/signature reset-approval research, with named Ingress stubs.

Run only in a networkless disposable Core image, never an installed Core.
No provider call, Supervisor token, frontend credential or existing config.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import re
import secrets
import socket
import tempfile
import time

from tools.ha_oauth_companion_lab.key_custody_probe import Locked, PrivateFiles, encoded
from tools.ha_oauth_companion_lab.recovery_probe import RecoveryVault


DOMAIN = "symphonia_native_reset_research"
FIELDS = {"request_id","installation","actor","pair_epoch","credential_epoch","profile","purpose","expires"}


def pack(value):
    return base64.b64encode(encoded(value)).decode()


def unpack(raw):
    if not isinstance(raw,str) or len(raw)>4096:
        raise Locked("bounded_approval_required")
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:
                raise Locked("duplicate_approval_field")
            result[key]=value
        return result
    try:
        return json.loads(base64.b64decode(raw,validate=True),object_pairs_hook=pairs)
    except Exception:
        raise Locked("invalid_approval") from None


class NativeSigner:
    """Synthetic trusted entry/key context; actor always comes from Core HTTP."""
    def __init__(self, directory, installation):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        self.directory,self.installation=directory,installation
        directory.mkdir(mode=0o700)
        key=ec.generate_private_key(ec.SECP256R1())
        self.public=key.public_key()
        self.canary=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        with PrivateFiles(directory) as files:
            files.publish("core.key",self.canary,exclusive=True)

    def prepare(self,raw,actor):
        request=unpack(raw)
        if (not isinstance(request,dict) or set(request)!=FIELDS or request.get("actor")!=actor
                or request.get("installation")!=self.installation or request.get("profile")!="oauth-key-recovery"
                or type(request.get("pair_epoch")) is not int or request["pair_epoch"]!=0
                or type(request.get("credential_epoch")) is not int or not 0<=request["credential_epoch"]<2**63
                or not isinstance(request.get("purpose"),str) or request["purpose"] not in {"reset","resume"}
                or not isinstance(request.get("request_id"),str) or re.fullmatch(r"[a-f0-9]{64}",request["request_id"]) is None
                or type(request.get("expires")) is not int or not time.time()<request["expires"]<=time.time()+30):
            raise Locked("native_reset_binding_refused")
        return request

    def sign(self,request,actor):
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        self.prepare(pack(request),actor)
        try:
            with PrivateFiles(self.directory) as files:
                key=serialization.load_pem_private_key(files.read("core.key",8192),password=None)
            if (not isinstance(key,ec.EllipticCurvePrivateKey) or not isinstance(key.curve,ec.SECP256R1)
                    or key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
                    !=self.public.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)):
                raise ValueError
            signature=key.sign(encoded(request),ec.ECDSA(hashes.SHA256()))
        except Exception:
            raise Locked("native_pair_key_unavailable") from None
        return pack({"request":request,"signature":base64.b64encode(signature).decode()})


class IngressStubConsumer:
    """TEST input stands in for trusted Ingress/browser/Origin/CSRF adaptation.

    Only Core actor/signature and durable reset ordering are real here. No
    source-IP/header or browser authorization proof is claimed by this class.
    """
    def __init__(self,vault,signer,actor):
        self.vault,self.signer,self.actor=vault,signer,actor
        self.clock=time.time
        self.csrf=secrets.token_urlsafe(32)
        self.browser=secrets.token_urlsafe(32)
        self.used=False
        self.request={"request_id":secrets.token_hex(32),"installation":signer.installation,
            "actor":actor,"pair_epoch":0,"credential_epoch":vault.snapshot()[0],
            "profile":"oauth-key-recovery","purpose":"reset","expires":int(time.time())+30}

    def submit(self,approval,*,actor,browser,csrf,origin):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        if (actor!=self.actor or browser!=self.browser or csrf!=self.csrf
                or origin!="https://ha-reset.example.invalid" or self.used):
            raise Locked("test_ingress_context_refused")
        decoded=unpack(approval)
        if not isinstance(decoded,dict) or set(decoded)!={"request","signature"}:
            raise Locked("approval_schema_refused")
        if encoded(decoded["request"])!=encoded(self.request) or not self.clock()<self.request["expires"]:
            raise Locked("approval_binding_refused")
        if self.vault.snapshot()[0]!=self.request["credential_epoch"]:
            raise Locked("approval_generation_refused")
        try:
            signature=base64.b64decode(decoded["signature"],validate=True)
            self.signer.public.verify(signature,encoded(self.request),ec.ECDSA(hashes.SHA256()))
        except Exception:
            raise Locked("approval_signature_refused") from None
        self.used=True  # Consume before durable intent/key publication.
        self.vault.explicit_reset(test_authorized=True)


FLOW_SOURCE='''
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import http
from homeassistant.components.http import KEY_HASS_USER
from tools.ha_oauth_companion_lab.native_reset_probe import Locked
DOMAIN="symphonia_native_reset_research"
def actor():
    request=http.current_request.get()
    user=request.get(KEY_HASS_USER) if request is not None else None
    return user.id if user and user.is_active and user.is_admin else None
class ResetFlow(config_entries.ConfigFlow,domain=DOMAIN):
    VERSION=1
    async def async_step_user(self,user_input=None):
        current=actor()
        if current is None:
            return self.async_abort(reason="missing_current_admin")
        if user_input is None:
            self.owner=current
            return self.async_show_form(step_id="user",data_schema=vol.Schema({vol.Required("request"):str}))
        if current!=self.owner:
            return self.async_abort(reason="wrong_actor")
        try:
            self.request=self.hass.data[DOMAIN].prepare(user_input["request"],current)
        except (Locked,KeyError):
            return self.async_abort(reason="invalid_reset_request")
        return self.async_show_form(step_id="confirm",data_schema=vol.Schema({vol.Required("confirm",default=False):bool}))
    async def async_step_confirm(self,user_input=None):
        current=actor()
        if current is None or current!=self.owner:
            return self.async_show_form(step_id="confirm",data_schema=vol.Schema({vol.Required("confirm",default=False):bool}),errors={"base":"wrong_actor"})
        if user_input and user_input.get("confirm") is True:
            try:
                approval=self.hass.data[DOMAIN].sign(self.request,current)
            except Locked:
                return self.async_abort(reason="approval_unavailable")
            return self.async_show_form(step_id="approval",data_schema=vol.Schema({}),description_placeholders={"approval":approval})
        return self.async_show_form(step_id="confirm",data_schema=vol.Schema({vol.Required("confirm",default=False):bool}))
    async def async_step_approval(self,user_input=None):
        return self.async_abort(reason="approval_view_closed")
'''


async def campaign():
    os.environ.clear()
    os.environ["PATH"]="/usr/local/bin:/usr/bin:/bin"
    from aiohttp import ClientSession
    from homeassistant import bootstrap,loader
    from homeassistant.auth.const import GROUP_ID_ADMIN,GROUP_ID_USER
    from homeassistant.const import __version__
    from homeassistant.core import HomeAssistant
    logging.getLogger().setLevel(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix="symphonia-native-reset-") as directory:
        root=Path(directory)
        component=root/"custom_components"/DOMAIN
        component.mkdir(parents=True)
        (component/"manifest.json").write_text(json.dumps({"domain":DOMAIN,"name":"Synthetic reset approval",
            "version":"0.0.0-lab","config_flow":True,"documentation":"https://example.invalid/",
            "requirements":[],"codeowners":[],"iot_class":"local_push"}))
        (component/"__init__.py").write_text("")
        (component/"config_flow.py").write_text(FLOW_SOURCE)
        signer=NativeSigner(root/"private-pair-key",secrets.token_hex(16))
        vault_root=root/"synthetic-app"
        RecoveryVault.create(vault_root)
        vault=RecoveryVault(vault_root)
        with socket.socket() as selection:
            selection.bind(("127.0.0.1",0));port=selection.getsockname()[1]
        hass=HomeAssistant(directory)
        loader.async_setup(hass)
        hass.config.skip_pip=True
        hass.data[DOMAIN]=signer
        results={}
        credentials=[]
        users=[]
        try:
            assert await bootstrap.async_from_config_dict({"http":{"server_host":"127.0.0.1","server_port":port},"api":{},"config":{}},hass) is hass
            await hass.async_start()
            await hass.auth.async_create_user("Synthetic owner",group_ids=[GROUP_ID_ADMIN])
            for name,group in (("Admin A",GROUP_ID_ADMIN),("Admin B",GROUP_ID_ADMIN),("Non-admin",GROUP_ID_USER)):
                user=await hass.auth.async_create_user(name,group_ids=[group])
                refresh=await hass.auth.async_create_refresh_token(user,client_id="https://reset.example.invalid")
                users.append(user);credentials.append([hass.auth.async_create_access_token(refresh),refresh])
            app=IngressStubConsumer(vault,signer,users[0].id)
            endpoint="/api/config/config_entries/flow"
            async with ClientSession() as client:
                async def call(path,payload,who=None):
                    headers={}
                    if who is not None:
                        headers["Authorization"]="Bearer "+credentials[who][0]
                    async with client.post(f"http://127.0.0.1:{port}"+path,json=payload,headers=headers) as response:
                        raw=await response.read()
                        return response.status,json.loads(raw) if response.content_type=="application/json" else {}
                async def begin(who=0):
                    status,flow=await call(endpoint,{"handler":DOMAIN},who)
                    assert status==200 and flow["type"]=="form"
                    path=endpoint+"/"+flow["flow_id"]
                    status,step=await call(path,{"request":pack(app.request)},who)
                    return path,status,step
                status,_=await call(endpoint,{"handler":DOMAIN})
                results["native_unauthenticated_denied"]=status==401
                status,denied=await call(endpoint,{"handler":DOMAIN},2)
                results["native_nonadmin_denied"]=status in (401,403) or denied.get("reason")=="missing_current_admin"
                _,status,other=await begin(1)
                results["different_admin_cannot_adopt_request"]=status==200 and other.get("reason")=="invalid_reset_request"
                path,status,step=await begin()
                assert status==200 and step["step_id"]=="confirm"
                status,wrong=await call(path,{"confirm":True},1)
                results["fresh_confirmation_same_actor"]=status==200 and wrong.get("errors",{}).get("base")=="wrong_actor"
                await hass.auth.async_update_user(users[0],is_active=False)
                status,_=await call(path,{"confirm":True},0)
                results["disabled_admin_cannot_approve"]=status==401
                await hass.auth.async_update_user(users[0],is_active=True)
                hass.auth.async_remove_refresh_token(credentials[0][1])
                status,_=await call(path,{"confirm":True},0)
                results["revoked_login_cannot_approve"]=status==401
                refresh=await hass.auth.async_create_refresh_token(users[0],client_id="https://reset.example.invalid")
                credentials[0]=[hass.auth.async_create_access_token(refresh),refresh]
                status,approved=await call(path,{"confirm":True},0)
                assert status==200 and approved["step_id"]=="approval"
                approval=approved["description_placeholders"]["approval"]
                results["fresh_same_admin_receives_signed_approval"]=True
                context={"actor":users[0].id,"browser":app.browser,"csrf":app.csrf,"origin":"https://ha-reset.example.invalid"}
                def rejects(document,changes=None):
                    try:
                        app.submit(document,**{**context,**(changes or {})})
                    except Locked:
                        return True
                    return False
                for label,changes in (("stub_wrong_origin",{"origin":"https://wrong.example.invalid"}),
                    ("stub_wrong_csrf",{"csrf":"wrong"}),("stub_other_actor",{"actor":users[1].id}),
                    ("stub_other_browser",{"browser":"wrong"})):
                    results[label]=rejects(approval,changes)
                altered=unpack(approval);altered["request"]["purpose"]="resume"
                results["changed_purpose_refused"]=rejects(pack(altered))
                altered=unpack(approval);altered["signature"]=base64.b64encode(b"wrong").decode()
                results["invalid_signature_refused"]=rejects(pack(altered))
                original_clock=app.clock;app.clock=lambda:original_clock()+31
                results["expired_approval_refused"]=rejects(approval)
                app.clock=original_clock
                before=vault.snapshot()[0]
                app.submit(approval,**context)
                results["signed_native_approval_admits_reset_once"]=vault.phase()=="unpaired" and vault.snapshot()[0]==before+1 and vault.read_all()=={}
                results["approval_replay_refused"]=rejects(approval) and vault.snapshot()[0]==before+1
                results["nonsecret_history_retained"]=vault.db.execute("SELECT value FROM history").fetchone()[0]=="retained-synthetic-history"
                from cryptography.hazmat.primitives import serialization
                from cryptography.hazmat.primitives.asymmetric import ec
                replacement=ec.generate_private_key(ec.SECP256R1()).private_bytes(serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
                for label,raw in (("malformed_core_key_locks",b"invalid-synthetic-key"),("replaced_core_key_locks",replacement)):
                    with PrivateFiles(signer.directory) as files:
                        files.publish("core.key",raw)
                    failed_path,_,_=await begin()
                    status,failed=await call(failed_path,{"confirm":True},0)
                    results[label]=status==200 and failed.get("reason")=="approval_unavailable" and (signer.directory/"core.key").read_bytes()==raw
                second_path,_,_=await begin()
                (signer.directory/"core.key").unlink()
                status,missing=await call(second_path,{"confirm":True},0)
                results["missing_core_key_locks_without_rekey"]=status==200 and missing.get("reason")=="approval_unavailable" and not (signer.directory/"core.key").exists()
                for flow in list(hass.config_entries.flow.async_progress()):
                    hass.config_entries.flow.async_abort(flow["flow_id"])
                await hass.async_block_till_done()
                results["no_config_entry_created"]=not hass.config_entries.async_entries(DOMAIN)
                files=[p for p in root.rglob("*") if p.is_file()]
                results["approval_and_private_key_absent_from_saved_files"]=all(signer.canary not in p.read_bytes() and approval.encode() not in p.read_bytes() for p in files)
            assert all(results.values()),[name for name,value in results.items() if not value]
            return {"mode":"isolated_real_core_reset_approval","core":__version__,"results":results,
                "real_provider_or_owner_ha":False,"supervisor_ingress_browser_context":"explicit test stub",
                "complete_ingress_reset_or_production_readiness_proven":False}
        finally:
            vault.close()
            await hass.async_stop()


if __name__=="__main__":
    try:
        print(json.dumps(asyncio.run(campaign()),sort_keys=True))
    except Exception as error:
        print(json.dumps({"mode":"native_reset_probe_failed","exception_type":type(error).__name__}))
        raise SystemExit(1) from None
