"""Disposable-Core-only harness for actual Supervisor Ingress/CSR wire.

Staged by an operator as a temporary custom component in symphonia-ha-lab.
Creates/removes only its synthetic users; no existing auth token is read.
"""
from __future__ import annotations

import asyncio
import hashlib
from http.client import HTTPSConnection
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import time
import traceback


DOMAIN="symphonia_native_reset_research"
SLUG="local_symphonia_oauth_recovery_wire"
ALIAS="local-symphonia-oauth-recovery-wire"
MARKER="symphonia-core-wire-approval-v1"
ORIGIN="http://127.0.0.1"


async def async_setup(hass,config):
    from homeassistant.const import __version__,EVENT_HOMEASSISTANT_STARTED
    from tools.ha_oauth_companion_lab.key_custody_probe import PrivateFiles
    root=Path(hass.config.config_dir)/".symphonia-wire-lab-v1"
    with PrivateFiles(root) as files:
        marker=json.loads(files.read("owned.json"))
    if marker.get("marker")!=MARKER or __version__!="2026.9.4":
        return False
    if (root/"receipt.json").exists():
        return True  # Never rerun synthetic setup merely because Core restarts.
    async def run(event=None):
        await exercise(hass,root)
    if hass.is_running:
        hass.async_create_task(run())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED,run)
    return True


async def exercise(hass,root):
    from aiohttp import ClientSession,DummyCookieJar,ClientTimeout
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    import cryptography
    from homeassistant.auth.const import GROUP_ID_ADMIN,GROUP_ID_USER
    from homeassistant.const import __version__
    from tools.ha_oauth_companion_lab.enrollment_probe import fingerprint,private,renewal_proof
    from tools.ha_oauth_companion_lab.key_custody_probe import PrivateFiles,encoded
    from tools.ha_oauth_companion_lab.native_reset_probe import NativeSigner,unpack,pack

    users=[];credentials=[];sessions=[];browser={};results={};failure=None;stage="setup_users"
    created_names=[];signer=None
    token=os.environ["SUPERVISOR_TOKEN"]
    def save(name,value):
        with PrivateFiles(root) as files:
            files.publish(name,encoded(value))
    async with ClientSession(cookie_jar=DummyCookieJar(),timeout=ClientTimeout(total=10)) as client:
        async def http(method,url,*,headers=None,value=None):
            data=encoded(value) if value is not None else None
            request_headers=dict(headers or {})
            if data is not None:
                request_headers["Content-Type"]="application/json"
            async with client.request(method,url,data=data,headers=request_headers,allow_redirects=False) as response:
                raw=await response.read()
                if len(raw)>65536:
                    raise RuntimeError("bounded_lab_response_required")
                body=json.loads(raw) if response.content_type=="application/json" else {}
                return response.status,body,response.headers
        async def supervisor(path,*,value=None):
            status,body,_=await http("POST" if value is not None else "GET","http://supervisor"+path,
                headers={"Authorization":"Bearer "+token},value=value)
            if status!=200 or body.get("result")!="ok":
                raise RuntimeError("lab_supervisor_request_failed")
            return body["data"]
        try:
            owners=[u for u in await hass.auth.async_get_users() if u.is_owner and u.is_active]
            assert len(owners)==1,"existing_disposable_owner_required"
            namespace="Symphonia wire lab "+secrets.token_hex(8)
            for suffix,group in (("A",GROUP_ID_ADMIN),("B",GROUP_ID_ADMIN),("nonadmin",GROUP_ID_USER)):
                name=namespace+" "+suffix
                user=await hass.auth.async_create_user(name,group_ids=[group])
                users.append(user);created_names.append(name)
                save("users.json",{"users":[{"id":u.id,"name":u.name} for u in users]})
                refresh=await hass.auth.async_create_refresh_token(user,client_id="https://wire.example.invalid")
                credentials.append([hass.auth.async_create_access_token(refresh),refresh])
                sessions.append((await supervisor("/ingress/session",value={"user_id":user.id}))["session"])
            stage="bootstrap_ingress"
            info=await supervisor("/addons/"+SLUG+"/info")
            path=info["ingress_url"].rstrip("/")
            assert re.fullmatch(r"/api/hassio_ingress/[A-Za-z0-9_-]+",path)
            assert info["state"]=="started"
            async def ingress(method="GET",endpoint="",*,who=0,value=None,changes=None,cookie_override=None,backend=False):
                cookies="ingress_session="+sessions[who]
                if who in browser:
                    cookies+="; symphonia_probe="+browser[who]
                headers={"Cookie":cookies if cookie_override is None else cookie_override}
                if method=="POST":
                    headers["Origin"]=ORIGIN
                headers.update(changes or {})
                if backend:
                    headers["X-Ingress-Path"]=path
                    url="http://supervisor/ingress/"+path.rsplit("/",1)[1]+"/"+endpoint
                else:
                    url=ORIGIN+path+"/"+endpoint
                status,body,response_headers=await http(method,url,headers=headers,value=value)
                for raw in response_headers.getall("Set-Cookie",[]):
                    parsed=SimpleCookie();parsed.load(raw)
                    if "symphonia_probe" in parsed:
                        browser[who]=parsed["symphonia_probe"].value
                return status,body
            status,_=await ingress(cookie_override="")
            results["ingress_without_session_denied"]=status==401
            status,_=await ingress(who=2)
            results["actual_supervisor_nonadmin_denied"]=status==403
            status,setup=await ingress()
            assert status==200 and setup["tls_available"] and isinstance(setup["challenge"],str)
            signer=NativeSigner(root/"core-keys",setup["installation"])
            hass.data[DOMAIN]=signer
            keyfile=root/"core-keys/core.key";certfile=root/"client.crt"
            server_pin=setup["server_pin"]
            def csr(key):
                return (x509.CertificateSigningRequestBuilder().subject_name(x509.Name([])).sign(key,hashes.SHA256())
                    .public_bytes(serialization.Encoding.PEM).decode())
            def tls(value,*,certificate=False,pin=None,route="/internal/ha-oauth/v1"):
                context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.minimum_version=ssl.TLSVersion.TLSv1_3
                context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
                if certificate:
                    context.load_cert_chain(str(certfile),str(keyfile))
                connection=HTTPSConnection(ALIAS,8098,context=context,timeout=5)
                try:
                    connection.connect()
                    observed=fingerprint(x509.load_der_x509_certificate(connection.sock.getpeercert(binary_form=True)).public_key())
                    if observed!=(pin or server_pin):
                        return "pin_refused_before_body",{}
                    connection.request("POST",route,encoded(value),{"Content-Type":"application/json"})
                    response=connection.getresponse();raw=response.read(16385)
                    assert len(raw)<=16384
                    return response.status,json.loads(raw)
                except OSError:
                    return "transport_unavailable",{}
                finally:
                    connection.close()
            async def call_tls(value,**kwargs):
                return await hass.async_add_executor_job(lambda:tls(value,**kwargs))
            with PrivateFiles(root/"core-keys") as files:
                key=serialization.load_pem_private_key(files.read("core.key",8192),password=None)
            stage="csr_wire"
            enroll={"version":1,"profile":"oauth","op":"pair.enroll","csr":csr(key),"challenge":setup["challenge"]}
            status,_=await call_tls(enroll,pin="0"*64)
            results["actual_wire_wrong_pin_before_body"]=status=="pin_refused_before_body"
            status,_=await call_tls({**enroll,"challenge":"wrong"})
            results["actual_wire_wrong_challenge_denied"]=status==403
            status,issued=await call_tls(enroll)
            assert status==200
            with PrivateFiles(root) as files:
                files.publish("client.crt",issued["certificate"].encode(),exclusive=True)
            results["actual_wire_csr_issued_for_core_key"]=fingerprint(x509.load_pem_x509_certificate(issued["certificate"].encode()).public_key())==fingerprint(signer.public)
            status,_=await call_tls(enroll)
            results["actual_wire_enrollment_replay_denied"]=status==403
            hello={"version":1,"profile":"oauth","op":"hello","epoch":0}
            status,_=await call_tls(hello,certificate=True)
            results["actual_core_to_app_generated_client_mtls"]=status==200
            status,_=await call_tls(hello)
            results["actual_wire_missing_client_denied"]=status==403
            for name,value in (("wrong_epoch",{**hello,"epoch":9}),("playback",{**hello,"profile":"playback"}),
                               ("unknown_operation",{**hello,"op":"core.proxy"})):
                status,_=await call_tls(value,certificate=True);results["actual_wire_"+name+"_denied"]=status==403
            status,_=await call_tls(hello,certificate=True,route="/reset")
            results["tls_cannot_reach_management"]=status==404
            stage="renewal_wire"
            replacement=ec.generate_private_key(ec.SECP256R1())
            renewal_csr=csr(replacement)
            current_der=x509.load_pem_x509_certificate(issued["certificate"].encode()).public_bytes(serialization.Encoding.DER)
            intent={**hello,"op":"pair.renew","csr":renewal_csr,"proof":renewal_proof(key,current_der,0,renewal_csr)}
            status,_=await call_tls(intent)
            results["copied_certificate_without_mtls_key_cannot_renew"]=status==403
            status,_=await call_tls({**intent,"proof":renewal_proof(replacement,current_der,0,renewal_csr)},certificate=True)
            results["renewal_rejects_wrong_key_signature_even_with_mtls"]=status==403
            status,renewed=await call_tls(intent,certificate=True)
            assert status==200
            status,_=await call_tls(hello,certificate=True)
            results["old_certificate_denied_after_wire_renewal"]=status==403
            with PrivateFiles(root/"core-keys") as files:
                files.publish("core.key",private(replacement))
            with PrivateFiles(root) as files:
                files.publish("client.crt",renewed["certificate"].encode())
            signer.public=replacement.public_key()
            status,_=await call_tls(hello,certificate=True)
            results["new_certificate_accepted_after_wire_renewal"]=status==200
            status,_,_=await http("GET",f"http://{ALIAS}:8099/",headers={"Cookie":"ingress_session="+sessions[0],
                "X-Remote-User-Id":users[0].id,"X-Ingress-Path":path})
            results["core_cannot_forge_ingress_peer"]=status==403
            stage="key_loss_gate"
            save("phase.json",{"phase":"paired","results":results,"core":__version__})
            deadline=time.monotonic()+180
            while not (root/"continue-after-key-loss.json").exists():
                if time.monotonic()>=deadline:
                    raise TimeoutError("owned_key_loss_gate_timed_out")
                await asyncio.sleep(0.5)
            with PrivateFiles(root) as files:
                gate=json.loads(files.read("continue-after-key-loss.json"))
                if gate=={"abort":True}:
                    raise RuntimeError("operator_aborted_fixture")
                assert gate=={"continue_after_key_loss":True}
            stage="native_ingress_reset"
            status,current=await ingress()
            assert status==200 and not current["tls_available"] and current["credentials_locked"]
            results["ingress_survives_private_key_loss"]=True
            status,_=await call_tls(hello,certificate=True)
            results["lost_private_keys_do_not_recreate_tls"]=status=="transport_unavailable"
            request=current["request"]
            async def native(endpoint,value,who=0):
                status,body,_=await http("POST",ORIGIN+endpoint,
                    headers={"Authorization":"Bearer "+credentials[who][0]},value=value)
                return status,body
            index="/api/config/config_entries/flow"
            async def begin(request):
                status,flow=await native(index,{"handler":DOMAIN})
                assert status==200 and flow["type"]=="form"
                endpoint=index+"/"+flow["flow_id"]
                status,step=await native(endpoint,{"request":request})
                assert status==200 and step.get("step_id")=="confirm"
                return endpoint
            endpoint=await begin(request)
            status,wrong=await native(endpoint,{"confirm":True},1)
            results["different_admin_cannot_sign_ingress_request"]=status==200 and wrong.get("errors",{}).get("base")=="wrong_actor"
            await hass.auth.async_update_user(users[0],is_active=False)
            status,_=await native(endpoint,{"confirm":True})
            results["disabled_native_admin_denied_despite_ingress"]=status==401
            cache_status,_=await ingress()
            results["ingress_after_disable_observed_status"]=cache_status
            await hass.auth.async_update_user(users[0],is_active=True)
            hass.auth.async_remove_refresh_token(credentials[0][1])
            status,_=await native(endpoint,{"confirm":True})
            results["revoked_native_login_denied"]=status==401
            refresh=await hass.auth.async_create_refresh_token(users[0],client_id="https://wire.example.invalid")
            credentials[0]=[hass.auth.async_create_access_token(refresh),refresh]
            status,approved=await native(endpoint,{"confirm":True})
            assert status==200 and approved.get("step_id")=="approval"
            approval=approved["description_placeholders"]["approval"]
            payload={"approval":approval,"csrf":current["csrf"]}
            status,_=await ingress("POST","reset",value={**payload,"csrf":"wrong"})
            results["actual_ingress_wrong_csrf_denied"]=status==403
            status,backend=await ingress(backend=True)
            results["actual_supervisor_backend_reaches_app"]=status==200 and backend.get("phase")==current["phase"]
            status,denied=await ingress("POST","reset",value=payload,changes={"Origin":"https://wrong.example.invalid"},backend=True)
            results["actual_backend_wrong_origin_denied"]=status==403 and denied.get("reason")=="reset_authority_refused"
            altered=unpack(approval);altered["signature"]="d3Jvbmc="
            status,_=await ingress("POST","reset",value={**payload,"approval":pack(altered)})
            results["actual_ingress_forged_approval_denied"]=status==403
            status,failed=await ingress("POST","reset",value=payload)
            assert status==503 and failed.get("phase")=="reset_pending"
            results["actual_ingress_interrupted_reset_pending"]=True
            status,_=await ingress("POST","reset",value=payload)
            results["actual_ingress_consumed_reset_replay_denied"]=status==403
            status,pending=await ingress()
            assert status==200 and pending["phase"]=="reset_pending"
            results["actual_ingress_fresh_request_is_resume"]=unpack(pending["request"])["purpose"]=="resume"
            endpoint=await begin(pending["request"])
            status,ready=await native(endpoint,{"confirm":True})
            assert status==200 and ready.get("step_id")=="approval"
            payload={"approval":ready["description_placeholders"]["approval"],"csrf":pending["csrf"]}
            status,completed=await ingress("POST","reset",value=payload)
            results["actual_ingress_native_resume_completes"]=status==200 and completed.get("phase")=="unpaired" and completed.get("pair_revoked") is True
            results["actual_ingress_history_retained"]=completed.get("history_retained") is True
            status,_=await ingress("POST","reset",value=payload)
            results["actual_ingress_resume_replay_denied"]=status==403
            status,post_reset=await ingress()
            results["completed_reset_never_offers_consumed_challenge"]=status==200 and post_reset.get("pairing_available") is False and "challenge" not in post_reset and post_reset.get("required_action")=="fresh_disposable_fixture"
            assert all(v for k,v in results.items() if k!="ingress_after_disable_observed_status"),[k for k,v in results.items() if k!="ingress_after_disable_observed_status" and not v]
        except Exception as error:
            failure=type(error).__name__
            save("failure-diagnostic.json",{"type":failure,"attribute":getattr(error,"name",None),
                "frames":[{"file":Path(f.filename).name,"line":f.lineno} for f in traceback.extract_tb(error.__traceback__)]})
        finally:
            for flow in list(hass.config_entries.flow.async_progress_by_handler(DOMAIN)):
                hass.config_entries.flow.async_abort(flow["flow_id"])
            hass.data.pop(DOMAIN,None)
            for user in users:
                await hass.auth.async_remove_user(user)
            await hass.async_block_till_done()
            receipt={"mode":"actual_core_supervisor_csr_and_ingress_reset","core":__version__,
                "cryptography":cryptography.__version__,"results":results,"error_type":failure,"stage":stage,
                "synthetic_users_removed":len(users),"no_existing_user_auth_token_read":True,
                "real_provider_or_owner_ha":False,"browser_cookie_semantics_proven":False}
            save("receipt.json",receipt)
            save("phase.json",{"phase":"complete" if failure is None else "failed","error_type":failure})
