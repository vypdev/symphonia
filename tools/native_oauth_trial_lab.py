"""Opt-in isolated package campaign; never target an owner Home Assistant."""
from __future__ import annotations
import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
DOMAIN = "symphonia_native_oauth_trial"
CORE = "ghcr.io/home-assistant/home-assistant@sha256:23f4dfbb69ce76315dbc4de7915504f1c2dcecd7ca2648113a493a385972e133"
LABEL = "native-trial-20261030"


class SyntheticProvider:
    """Only this lab composition injects a provider; shipping main cannot."""
    def __init__(self, root):
        self.root = root
    def count(self, operation):
        p = self.root / "provider-counts.json"
        value = json.loads(p.read_text()) if p.exists() else {"exchange": 0, "refresh": 0, "account": 0}
        value[operation] += 1
        p.write_text(json.dumps(value))
    async def exchange(self, binding, code, verifier):
        from symphonia_native_oauth_trial.application import Grant
        assert code == "synthetic-package-code"
        expected = (self.root / "expected-challenge").read_text()
        assert base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode() == expected
        self.count("exchange")
        return Grant("synthetic-access-canary", "synthetic-refresh-canary", 3600)
    async def refresh(self, binding, grant):
        from symphonia_native_oauth_trial.application import Grant
        assert grant.refresh == "synthetic-refresh-canary"
        self.count("refresh")
        return Grant("synthetic-replacement-canary", grant.refresh, 7200)
    async def account(self, binding, grant):
        self.count("account")
        return hashlib.sha256(b"synthetic-stable-account").hexdigest()


async def app_fixture(directory, fresh):
    from symphonia_native_oauth_trial.run import compose, serve
    root = Path(directory)
    clock_file = root.parent / "fixture-clock"
    import time
    clock = lambda: float(clock_file.read_text()) if clock_file.exists() else time.time()
    server = compose(root, SyntheticProvider(root.parent), fresh=fresh, clock=clock)
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    print("fixture_ready", flush=True)
    await serve(server, stop, host="127.0.0.1")


async def core_campaign():
    # Core must load the installed artifact, not this checkout's namespace.
    sys.path[:] = [item for item in sys.path if Path(item or '.').resolve() != REPO]
    os.environ.clear()
    os.environ["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    logging.getLogger().setLevel(logging.CRITICAL)
    from aiohttp import ClientSession
    from homeassistant import bootstrap, loader
    from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
    from homeassistant.core import HomeAssistant
    from homeassistant.const import __version__
    from homeassistant.helpers import config_entry_oauth2_flow as oauth
    assert __version__ == "2026.10.4"
    results = {}
    with tempfile.TemporaryDirectory(prefix="native-trial-package-") as directory:
        root = Path(directory)
        ha_root = root / "ha"; ha_root.mkdir()
        (ha_root / ".HA_VERSION").write_text(__version__)
        installer = REPO / "tools/install_native_oauth_trial_helper.sh"
        def install(mode):
            return subprocess.run(["sh", str(installer), mode, str(ha_root)], capture_output=True, timeout=10)
        installed = install("install")
        assert installed.returncode == 0, ("install", installed.stderr.decode()[-2000:])
        helper = ha_root / "custom_components" / DOMAIN
        unrelated = ha_root / "custom_components/unrelated"; unrelated.mkdir(); (unrelated / "sentinel").write_text("preserve")
        assert install("install").returncode != 0
        original = (helper / "bridge.py").read_bytes()
        (helper / "bridge.py").write_bytes(original + b"\n# modified\n")
        assert install("remove").returncode != 0 and (helper / "config_flow.py").exists()
        (helper / "bridge.py").write_bytes(original)
        (helper / "unexpected").write_text("unowned")
        assert install("remove").returncode != 0 and (helper / "config_flow.py").exists()
        (helper / "unexpected").unlink()
        results["installer_conflicts_preserve_source_and_unrelated"] = True
        with socket.socket() as selection:
            selection.bind(("127.0.0.1", 0)); port = selection.getsockname()[1]
        app_root = root / "app"; app_root.mkdir(mode=0o700)
        child = None
        async def start_app(fresh=False):
            nonlocal child
            child = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__)), "--app-fixture", str(app_root), *( ["--fresh"] if fresh else []), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            line = await asyncio.wait_for(child.stdout.readline(), 10)
            assert line == b"fixture_ready\n", ("app_boot", child.returncode)
            # Readiness is a local listener probe, never a provider call.
            for _ in range(30):
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", 8099)
                    writer.close(); await writer.wait_closed(); break
                except OSError:
                    await asyncio.sleep(.02)
            else: raise AssertionError("fixture_not_listening")
        async def stop_app():
            nonlocal child
            if child and child.returncode is None:
                child.terminate(); await asyncio.wait_for(child.wait(), 5)
        def counts():
            p = root / "provider-counts.json"
            return json.loads(p.read_text()) if p.exists() else {"exchange": 0, "refresh": 0, "account": 0}
        await start_app(True)
        identity = json.loads((app_root / "identity.json").read_text())
        challenge = (app_root / "oauth_keys/bootstrap.challenge").read_text()
        bundle = json.dumps({"installation":identity["installation"], "pin":identity["server_pin"], "challenge":challenge, "deadline":identity["deadline"], "profile":"trial_read_private"})
        hass = HomeAssistant(str(ha_root)); loader.async_setup(hass); hass.config.skip_pip = True
        trap_calls = []
        async def trap(*args, **kwargs):
            trap_calls.append(True); raise AssertionError("default_token_path_forbidden")
        oauth.LocalOAuth2Implementation.async_resolve_external_data = trap
        oauth.OAuth2Session.async_ensure_token_valid = trap
        users=[]; tokens=[]
        coverage = fixture_coverage([str(helper / '*.py')])
        try:
            assert await bootstrap.async_from_config_dict({"http":{"server_host":"127.0.0.1","server_port":port},"api":{},"config":{},"auth":{},"my":{}},hass) is hass
            await hass.async_start()
            await hass.auth.async_create_user("Synthetic lab owner", group_ids=[GROUP_ID_ADMIN])
            for name, group in [("Admin A",GROUP_ID_ADMIN),("Admin B",GROUP_ID_ADMIN),("Ordinary",GROUP_ID_USER)]:
                user=await hass.auth.async_create_user(name, group_ids=[group])
                refresh=await hass.auth.async_create_refresh_token(user,client_id="https://package.example.invalid")
                users.append(user); tokens.append([hass.auth.async_create_access_token(refresh),refresh])
            endpoint="/api/config/config_entries/flow"
            async with ClientSession() as client:
                async def call(method,path,payload=None,who=None,params=None):
                    headers={} if who is None else {"Authorization":"Bearer "+tokens[who][0]}
                    async with client.request(method,f"http://127.0.0.1:{port}"+path,json=payload,params=params,headers=headers) as response:
                        raw=await response.read()
                        value=json.loads(raw) if response.content_type=="application/json" else {}
                        return response.status,value
                async def posted(path,payload,who=0):
                    status,value=await call("POST",path,payload,who)
                    assert status==200,("native_post",status,value.get("type"),value.get("reason"))
                    return value
                assert (await call("POST",endpoint,{"handler":DOMAIN}))[0]==401
                form=await posted(endpoint,{"handler":DOMAIN})
                assert form.get("step_id")=="user",("pair_form",form.get("reason"),form.get("type"))
                flow_path=endpoint+"/"+form["flow_id"]
                entry_result=await posted(flow_path,{"app_slug":"local_symphonia_native_oauth_trial","client_id":"synthetic-public-client","bootstrap":bundle,"encrypted_core_backups":True})
                assert entry_result.get("type")=="create_entry",("pair",entry_result.get("reason"),entry_result.get("errors"))
                await hass.async_block_till_done()
                entry=hass.config_entries.async_entries(DOMAIN)[0]
                assert entry.state.value=="loaded",("entry",entry.state.value)
                # Exact production allowlist must accept Core's stored representation.
                module=__import__("custom_components."+DOMAIN+".bridge",fromlist=["validate_reference"])
                assert Path(module.__file__).parent == helper, "installed_helper_origin_required"
                module.validate_reference(entry.data)
                async def reconfigure(operation,who=0):
                    form=await posted(endpoint,{"handler":DOMAIN,"entry_id":entry.entry_id},who)
                    assert form.get("step_id")=="reconfigure",("menu",form.get("type"),form.get("reason"))
                    path=endpoint+"/"+form["flow_id"]
                    confirm=await posted(path,{"operation":operation},who)
                    assert confirm.get("step_id")==operation,("operation",confirm.get("type"),confirm.get("reason"))
                    return path
                path=await reconfigure("connect")
                external=await posted(path,{"confirm":True})
                assert external.get("type")=="external",("external",external.get("reason"))
                params=parse_qs(urlsplit(external["url"]).query)
                assert params["redirect_uri"]==[oauth.MY_AUTH_CALLBACK_PATH] and params["scope"]==["user-read-private"] and params["code_challenge_method"]==["S256"]
                (root/"expected-challenge").write_text(params["code_challenge"][0])
                assert counts()["exchange"]==0
                invalid={"state":{"flow_id":external["flow_id"],"redirect_uri":oauth.MY_AUTH_CALLBACK_PATH},"code":"synthetic-package-code"}
                # Forged native input must never stage or exchange; exercise a separate flow
                # at the auth step would intentionally abort this one, so prove callback
                # invalid signature on the real route before its single valid return.
                assert (await call("GET",oauth.AUTH_CALLBACK_PATH,params={"state":"invalid-signature","code":"synthetic-package-code"}))[0]==400
                assert (await call("GET",oauth.AUTH_CALLBACK_PATH,params={"state":params["state"][0],"code":"synthetic-package-code"}))[0]==200
                assert counts()=={"exchange":0,"refresh":0,"account":0}
                status,form=await call("GET",path,who=0)
                assert status==200 and form.get("step_id")=="confirm",("resume",form.get("type"),form.get("reason"))
                assert (await call("POST",path,{"confirm":True}))[0]==401
                assert (await call("POST",path,{"confirm":True},2))[0] in (401,403)
                assert (await posted(path,{"confirm":True},1)).get("errors",{}).get("base")=="administrator_required"
                await hass.auth.async_update_user(users[0],is_active=False)
                assert (await call("POST",path,{"confirm":True},0))[0]==401
                await hass.auth.async_update_user(users[0],is_active=True)
                hass.auth.async_remove_refresh_token(tokens[0][1])
                assert (await call("POST",path,{"confirm":True},0))[0]==401
                refresh=await hass.auth.async_create_refresh_token(users[0],client_id="https://package.example.invalid")
                tokens[0]=[hass.auth.async_create_access_token(refresh),refresh]
                assert counts()["exchange"]==0
                results["package_C01_real_core_actor_guards"]=True
                results["package_C02_real_core_callback_stages_only"]=True
                completed=await posted(path,{"confirm":True})
                assert completed.get("reason")=="oauth_active",("complete",completed.get("reason"))
                assert counts()=={"exchange":1,"refresh":0,"account":1}
                assert (await call("POST",path,{"confirm":True},0))[0] in (400,404)
                assert counts()["exchange"]==1
                for file in ha_root.rglob("*"):
                    if file.is_file() and file.suffix!=".pyc":
                        raw=file.read_bytes()
                        assert not any(x in raw for x in (b"synthetic-access-canary",b"synthetic-refresh-canary",b"synthetic-package-code"))
                assert b"synthetic-refresh-canary" not in (app_root/"trial.sqlite").read_bytes()
                assert not trap_calls
                results["package_C04_same_source_native_tls_sealed_grant"]=True
                await stop_app(); await start_app()
                restarted=json.loads((app_root/"identity.json").read_text())
                assert restarted==identity
                path=await reconfigure("refresh")
                result=await posted(path,{"confirm":True})
                assert result.get("reason")=="trial_verified",("refresh",result.get("reason"))
                assert counts()=={"exchange":1,"refresh":1,"account":2}
                assert not trap_calls
                results["package_C05_process_restart_confirmed_refresh"]=True
                assert await helper_failure_contracts(hass,entry)
                path=await reconfigure("retire",1)
                from unittest.mock import patch
                channel_module=__import__('custom_components.'+DOMAIN+'.bridge',fromlist=['Bridge'])
                original_call=channel_module.Bridge.call
                retire_replies=[]
                async def observe_retire(channel,payload,**kwargs):
                    value=await original_call(channel,payload,**kwargs)
                    if payload.get('op')=='pair.revoke':retire_replies.append(value.get('phase'))
                    return value
                with patch.object(channel_module.Bridge,'call',observe_retire):
                    result=await posted(path,{"confirm":True},1)
                assert retire_replies==['retired']
                assert result.get("reason")=="trial_retired",("retire",result.get("reason"))
                assert entry.data.get("retired") is True and entry.data.get("key_cleanup_pending") is False
                assert not (ha_root/".storage"/DOMAIN/identity["installation"]).exists()
                await stop_app()
                await start_expired(app_root)  # Retirement survives process restart.
                assert json.loads((app_root/"identity.json").read_text())==identity
                assert await hass.config_entries.async_remove(entry.entry_id)
                # A second explicitly fresh *lab* installation isolates expiry
                # from retirement; it never starts consent or contacts a provider.
                app_root = root / "deadline-app"; app_root.mkdir(mode=0o700)
                await start_app(True)
                deadline_identity=json.loads((app_root/"identity.json").read_text())
                await stop_app(); await start_app()
                assert json.loads((app_root/"identity.json").read_text())==deadline_identity
                # Advance only this disposable App's test clock; no host clock changes.
                (root/"fixture-clock").write_text(str(deadline_identity["deadline"]))
                await asyncio.wait_for(child.wait(),4)
                assert child.returncode==0
                # A new process at the same original deadline must refuse reopening.
                await start_expired(app_root)
                assert counts()=={"exchange":1,"refresh":1,"account":2}
                results["package_C08_deadline_retire_no_rebootstrap"]=True
            await hass.async_stop()
            # Runtime cache ownership comes from the actual packaged helper.
            assert (helper/".cache-owned.sha256").exists()
            receipt=helper/".cache-owned.sha256"
            lines=receipt.read_text().splitlines()
            if len(lines)==1:
                # Explicit synthetic installer fixture when Core writes no pyc.
                cache=helper/"__pycache__";cache.mkdir(exist_ok=True)
                canary=cache/"keys.cpython-314.pyc"
                assert not canary.exists()
                canary.write_bytes(b"synthetic-installer-cache-canary")
                lines.append(hashlib.sha256(canary.read_bytes()).hexdigest()+"  "+canary.relative_to(helper).as_posix())
            valid_receipt="\n".join(lines)+"\n"
            intact={p.relative_to(helper):p.read_bytes() for p in helper.rglob('*') if p.is_file() and p!=receipt}
            for invalid_receipt in (valid_receipt+lines[1]+"\n", ""):
                receipt.write_text(invalid_receipt)
                assert install("remove").returncode!=0
                assert all((helper/p).read_bytes()==raw for p,raw in intact.items())
            receipt.write_text(valid_receipt)
            assert install("remove").returncode==0
            assert not helper.exists() and (unrelated/"sentinel").read_text()=="preserve"
            results["package_C07_hash_installer_owned_rollback"]=True
            return {"mode":"isolated_exact_source_package_core","core":__version__,"results":results,"boundaries":{"provider":"test-only injected synthetic port","dns":"Docker hosts entry maps fixed production alias to loopback","my":"actual Core My component; external relay/browser untested","app_restart":"actual child process","owner_ha":"unused","supervisor_topology_backup":"separate required campaign"}}
        finally:
            if hass.state.value!="not_running":
                await hass.async_stop()
            await stop_app()
            if coverage:
                coverage.stop(); coverage.save()


async def start_expired(app_root):
    child=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__)),"--app-fixture",str(app_root),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    await asyncio.wait_for(child.wait(),5)
    assert child.returncode!=0
    assert b"fixture_ready" not in await child.stdout.read()


def fixture_coverage(extra=()):
    if not Path('/evidence/.coverage-owned').is_file():
        return None
    sys.path.insert(0, '/coverage-lib')
    os.environ['COVERAGE_CORE']='pytrace'
    from coverage import Coverage
    coverage=Coverage(branch=True,include=[str(REPO/'symphonia_native_oauth_trial'/'*.py'),*extra],
        data_file='/evidence/.coverage-package',data_suffix=True,config_file=False)
    coverage.start()
    return coverage


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-fixture",action="store_true")
    parser.add_argument("--app-fixture",type=Path)
    parser.add_argument("--fresh",action="store_true")
    args=parser.parse_args()
    if args.app_fixture:
        coverage=fixture_coverage()
        try:
            asyncio.run(app_fixture(args.app_fixture,args.fresh))
        finally:
            if coverage:
                coverage.stop(); coverage.save()
        return
    if args.core_fixture:
        try:
            print(json.dumps(asyncio.run(core_campaign()),sort_keys=True))
        except BaseException as error:
            import traceback
            print(json.dumps({"mode":"package_campaign_failed","type":type(error).__name__,"safe_assertion":str(error) if isinstance(error,AssertionError) else None,"locations":[{"file":Path(x.filename).name,"line":x.lineno,"function":x.name} for x in traceback.extract_tb(error.__traceback__)]}))
            raise SystemExit(1) from None
        return
    parser.error("Explicit lab fixture mode required; never use on owner HA")


# Host-side explicit operators are imported by the opt-in packaging tests.
CONTAINER = 'symphonia-ha-lab'
SLUG = 'local_symphonia_native_oauth_trial'
APP_STAGE = '/mnt/supervisor/apps/local/symphonia_native_oauth_trial'


def lab_call(arguments, *, data=None, timeout=600, check=True):
    result = subprocess.run(arguments, input=data, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('guarded_lab_operation_failed_' + str(result.returncode))
    return result


def supervisor_guard():
    from tools.ha_app_lab import _container_details, _is_lab_container
    details = _container_details()
    if not details or not _is_lab_container(details) or details['running'] != 'true':
        raise RuntimeError('owned_supervisor_lab_required')
    supervisor = lab_ha('supervisor', 'info', guarded=False)
    core = lab_ha('core', 'info', guarded=False)
    if supervisor['version'] != '2026.10.5' or core['version'] != '2026.10.4' or core['arch'] != 'aarch64':
        raise RuntimeError('exact_lab_matrix_required')
    return {'core':core['version'], 'supervisor':supervisor['version'], 'arch':core['arch']}


def lab_ha(*args, guarded=True):
    if guarded:
        supervisor_guard()
    response=lab_call(['docker','exec',CONTAINER,'ha',*args,'--raw-json'])
    value=json.loads(response.stdout)
    if value.get('result') != 'ok':
        raise RuntimeError('guarded_supervisor_api_failed')
    return value.get('data')


def stage_supervisor(output):
    supervisor_guard()
    from tools.stage_native_oauth_trial import stage
    receipt=stage(output)
    exists=lab_call(['docker','exec',CONTAINER,'test','-e',APP_STAGE],check=False)
    if exists.returncode == 0:
        raise RuntimeError('existing_lab_app_stage_refused')
    lab_call(['docker','cp',str(output/'app'),CONTAINER+':'+APP_STAGE])
    checked=lab_call(['docker','exec','--workdir',APP_STAGE,CONTAINER,'sha256sum','-c','SHA256SUMS'])
    if len(checked.stdout.splitlines()) != 12:
        raise RuntimeError('staged_manifest_count_mismatch')
    reload=lab_call(['docker','exec',CONTAINER,'ha','store','reload','--raw-json'],check=False)
    if reload.returncode and b'context deadline exceeded' not in reload.stderr:
        raise RuntimeError('lab_store_reload_failed')
    info=lab_ha('apps','info',SLUG)
    if info.get('slug')!=SLUG or info.get('version_latest')!='0.1.0b1' or not info.get('available'):
        raise RuntimeError('exact_local_store_app_not_ready')
    if info.get('version') is not None:
        raise RuntimeError('existing_lab_install_refused')
    receipt['lab_store_reload_acknowledged']=reload.returncode==0
    return receipt




def supervisor_channel():
    matrix=supervisor_guard()
    # Install the same hash-checked helper artifact into the disposable Core.
    installer=REPO/'tools/install_native_oauth_trial_helper.sh'
    publish="from pathlib import Path; import sys; p=Path('/tmp/symphonia-native-helper-installer.sh'); raw=sys.stdin.buffer.read(); assert not p.is_symlink(); assert not p.exists() or p.read_bytes()==raw; p.write_bytes(raw)"
    lab_call(['docker','exec','-i',CONTAINER,'docker','exec','-i','homeassistant','python3','-c',publish],data=installer.read_bytes())
    existing=lab_call(['docker','exec',CONTAINER,'docker','exec','homeassistant','test','-d','/config/custom_components/'+DOMAIN],check=False)
    if existing.returncode:
        lab_call(['docker','exec',CONTAINER,'docker','exec','homeassistant','sh','/tmp/symphonia-native-helper-installer.sh','install','/config'])
    else:
        from tools.stage_native_oauth_trial import source_manifest,HELPER_FILES,digest
        expected=digest(source_manifest({name:(REPO/'custom_components'/DOMAIN/name).read_bytes() for name in HELPER_FILES}))
        verify="from pathlib import Path; import hashlib; p=Path('/config/custom_components/"+DOMAIN+"/.source-owned.sha256'); assert not p.is_symlink(); assert hashlib.sha256(p.read_bytes()).hexdigest()=='"+expected+"'"
        lab_call(['docker','exec',CONTAINER,'docker','exec','homeassistant','python3','-c',verify])
    info=lab_ha('apps','info',SLUG)
    assert info['version']=='0.1.0b1' and info['boot']=='manual'
    if info.get('state')!='started':
        lab_ha('apps','start',SLUG)
    inspected=json.loads(lab_call(['docker','exec',CONTAINER,'docker','inspect','app_'+SLUG]).stdout)[0]
    assert not inspected['HostConfig']['Privileged'] and not inspected['HostConfig']['PortBindings']
    assert not inspected['HostConfig']['NetworkMode']=='host'
    import time
    for _ in range(50):
        ready=lab_call(['docker','exec',CONTAINER,'docker','exec','app_'+SLUG,'stat','-c','%a:%u','/data/native_trial'],check=False)
        if not ready.returncode:
            user=ready.stdout.decode().splitlines();break
        time.sleep(.1)
    else:
        raise RuntimeError('lab_app_not_ready')
    # docker exec runs as image root; the service process must actually drop UID.
    service=lab_call(['docker','exec',CONTAINER,'docker','exec','app_'+SLUG,'python','-c',"from pathlib import Path; import json; print(json.dumps({'uid':int(next(x for x in Path('/proc/1/status').read_text().splitlines() if x.startswith('Uid:')).split()[1])}))"])
    identity=json.loads(service.stdout)
    assert identity['uid']==10001 and user[-1]=='700:10001'
    # A real Supervisor-origin request exercises the App's peer restriction.
    # Identity headers are a synthetic fixture, not proof of a HA browser login.
    script='''import asyncio,json,html,re
from aiohttp import ClientSession
async def main():
 async with ClientSession() as c:
  async with c.get('http://local-symphonia-native-oauth-trial:8099/',headers={'X-Ingress-Path':'/api/hassio_ingress/syntheticpackagefixture32','X-Remote-User-Id':'syntheticadmin','X-Remote-User-Groups':'system-admin'}) as r:
   assert r.status==200
   text=await r.text(); m=re.search(r"<pre tabindex='0'>(.*?)</pre>",text,re.S); assert m
   print(json.dumps(json.loads(html.unescape(m.group(1)))))
asyncio.run(main())'''
    bundle=json.loads(lab_call(['docker','exec',CONTAINER,'docker','exec','hassio_supervisor','python3','-c',script]).stdout)
    core_script='''import asyncio,json,sys,ssl
from pathlib import Path
sys.path.insert(0,'/config')
from custom_components.symphonia_native_oauth_trial.bridge import Bridge,BridgeError
from custom_components.symphonia_native_oauth_trial.keys import CoreKeys
x=json.load(sys.stdin)
async def main():
 keys=CoreKeys(Path('/tmp/symphonia-native-package-core-key32-'+x['installation']))
 csr=keys.create_csr(x['installation'],'syntheticadmin')
 wrong=Bridge('local_symphonia_native_oauth_trial','0'*64,x['deadline'],keys)
 try: await wrong.call({'version':1,'op':'pair.enroll','actor':'syntheticadmin','challenge':x['challenge'],'csr':csr},paired=False)
 except BridgeError: pass
 else: raise AssertionError('wrong_pin_admitted')
 bridge=Bridge('local_symphonia_native_oauth_trial',x['pin'],x['deadline'],keys)
 response=await bridge.call({'version':1,'op':'pair.enroll','actor':'syntheticadmin','challenge':x['challenge'],'csr':csr},paired=False)
 keys.accept(response['ca'],response['certificate'],installation=x['installation'],pair_id=response['pair_id'],deadline=x['deadline'],server_der=bridge.server_der)
 status=await bridge.call({'version':1,'op':'status','pair_id':response['pair_id']})
 assert status['phase']=='paired'
 try: await bridge.call({'version':1,'op':'provider.raw','pair_id':response['pair_id']})
 except BridgeError: pass
 else: raise AssertionError('raw_operation_admitted')
 try: await bridge.call({'version':1,'op':'status','pair_id':'wrong-pair'})
 except BridgeError: pass
 else: raise AssertionError('wrong_pair_admitted')
 # No client certificate: refuse before a private RPC body is sent.
 context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
 reader,writer=await asyncio.open_connection('local-symphonia-native-oauth-trial',8098,ssl=context)
 writer.write(b'POST /internal/ha-oauth/v1 HTTP/1.1\\r\\nHost: local-symphonia-native-oauth-trial\\r\\nContent-Type: application/json\\r\\nContent-Length: 100\\r\\n\\r\\n');await writer.drain()
 head=await asyncio.wait_for(reader.readuntil(b'\\r\\n\\r\\n'),4)
 assert head.startswith(b'HTTP/1.1 403')
 writer.close();await writer.wait_closed()
 keys.remove_owned(keys.hashes())
 from custom_components.symphonia_native_oauth_trial import record_runtime_cache
 record_runtime_cache()
 print(json.dumps({'paired':True,'wrong_pin_denied':True,'wrong_pair_denied':True,'raw_operation_denied':True,'unauthenticated_rpc_denied_before_body':True}))
asyncio.run(main())'''
    value=json.loads(lab_call(['docker','exec','-i',CONTAINER,'docker','exec','-i','homeassistant','python3','-c',core_script],data=json.dumps(bundle).encode()).stdout)
    return {'matrix':matrix,'results':{'package_C03_actual_supervisor_alias_csr_mtls':all(value.values())},'channel':value,'service_uid':identity['uid'],'host_ports':False,'boundary':'Ingress identity headers are synthetic; owner HA unused'}


def supervisor_backup():
    supervisor_guard()
    image=json.loads(lab_call(['docker','exec',CONTAINER,'docker','inspect','app_'+SLUG]).stdout)[0]['Image']
    import re
    if re.fullmatch(r'sha256:[a-f0-9]{64}',image) is None:
        raise RuntimeError('lab_image_identity_required')
    data_path='/mnt/supervisor/apps/data/'+SLUG
    lab_ha('apps','stop',SLUG)
    seal='''import asyncio,hashlib,json
from pathlib import Path
from symphonia_native_oauth_trial.run import compose
from symphonia_native_oauth_trial.policy import Binding,PROFILE,REDIRECT
from symphonia_native_oauth_trial.application import Grant
class Synthetic:
 async def exchange(self,b,c,v): return Grant('backup-access-canary','backup-refresh-canary',3600)
 async def account(self,b,g): return hashlib.sha256(b'backup-synthetic-account').hexdigest()
async def main():
 s=compose(Path('/data/native_trial'),Synthetic());m=s.state.meta();assert m['bootstrap_used'] and m['pair_id']
 b=Binding(m['installation'],m['pair_id'],m['actor'],'offline-backup-flow','offline-backup-attempt',m['pair_epoch'],m['credential_epoch'],'spotify','synthetic-backup-client',PROFILE,REDIRECT,m['deadline'])
 row=s.state.db.execute('SELECT phase,binding FROM attempt WHERE id=1').fetchone()
 if row is None:
  s.trial.start(b,'v'*64);s.trial.stage(b,'synthetic-backup-code');result=await s.trial.complete(b)
  assert result['phase']=='active'
 else:
  assert row['phase']=='active' and Binding.parse(json.loads(row['binding']))==b
 sealed,_=s.state.grant(b,s.clock());assert b'backup-refresh-canary' not in sealed
 s.state.close();print(json.dumps({'sealed':True,'deadline':m['deadline'],'installation':m['installation'],'sealed_sha256':hashlib.sha256(sealed).hexdigest()}))
asyncio.run(main())'''
    before=json.loads(lab_call(['docker','exec',CONTAINER,'docker','run','--rm','--network','none','--user','10001:10001','--mount','type=bind,src='+data_path+',dst=/data','--entrypoint','python',image,'-c',seal]).stdout)
    lab_ha('apps','start',SLUG)
    backup=lab_ha('backups','new','--app',SLUG,'--name','Symphonia-native-trial-synthetic-package32','--uncompressed')
    slug=backup['slug']
    assert re.fullmatch('[a-f0-9]{8}',slug)
    inspect='''from pathlib import Path
import io,json,sys,tarfile
p=Path('/stage')/(sys.argv[1]+'.tar');assert p.is_file() and not p.is_symlink()
with tarfile.open(p) as outer:
 members=[x for x in outer.getmembers() if x.isfile() and x.name.endswith(('.tar.gz','.tar'))]
 assert len(members)==1,[x.name for x in members]
 raw=outer.extractfile(members[0]).read()
 with tarfile.open(fileobj=io.BytesIO(raw)) as inner:
  names=[x.name for x in inner.getmembers() if x.isfile()]
  assert any(x.endswith('native_trial/trial.sqlite') for x in names),names
  assert not any('/oauth_keys/' in x for x in names),names
  for member in inner.getmembers():
   if member.isfile():
    data=inner.extractfile(member).read()
    assert b'backup-access-canary' not in data and b'backup-refresh-canary' not in data
  print(json.dumps({'real_supervisor_backup':True,'key_files':0,'no_plaintext_grant':True,'file_count':len(names)}))
'''
    archive=json.loads(lab_call(['docker','exec',CONTAINER,'docker','run','--rm','--network','none','--mount','type=bind,src=/mnt/supervisor/backup,dst=/stage,readonly','--entrypoint','python',image,'-c',inspect,slug]).stdout)
    # Uninstall only this named disposable App: restore cannot reuse its old keys.
    lab_ha('apps','uninstall',SLUG)
    lab_ha('backups','restore',slug,'--app',SLUG)
    restored='''from pathlib import Path
import hashlib,json,sqlite3,sys
root=Path('/data/native_trial');identity=json.loads((root/'identity.json').read_text())
assert not (root/'oauth_keys').exists() or not list((root/'oauth_keys').iterdir())
db=sqlite3.connect('file:'+str(root/'trial.sqlite')+'?mode=ro',uri=True)
sealed=db.execute('SELECT sealed FROM attempt WHERE id=1').fetchone()[0];db.close()
print(json.dumps({'installation':identity['installation'],'deadline':identity['deadline'],'sealed_sha256':hashlib.sha256(sealed).hexdigest(),'keys_absent':True}))'''
    after=json.loads(lab_call(['docker','exec',CONTAINER,'docker','run','--rm','--network','none','--mount','type=bind,src='+data_path+',dst=/data,readonly','--entrypoint','python',image,'-c',restored]).stdout)
    assert all(before[name]==after[name] for name in ('installation','deadline','sealed_sha256'))
    # Execute the actual shipping entrypoint against restored data, with no network.
    boot=lab_call(['docker','exec',CONTAINER,'docker','run','--rm','--network','none','--mount','type=bind,src='+data_path+',dst=/data',image],check=False)
    assert boot.returncode==78 and json.loads(boot.stdout)=={'phase':'locked'},(boot.returncode,boot.stdout.decode()[:100])
    again=json.loads(lab_call(['docker','exec',CONTAINER,'docker','run','--rm','--network','none','--mount','type=bind,src='+data_path+',dst=/data,readonly','--entrypoint','python',image,'-c',restored]).stdout)
    assert again==after
    return {'results':{'package_C06_real_supervisor_backup_locked_restore':True},'archive':archive,'same_original_deadline':True,'same_sealed_grant':True,'keys_regenerated':False,'shipping_main_exit':boot.returncode,'backup_slug':slug,'boundary':'Synthetic grant only; unencrypted disposable App backup; no owner archive read'}


async def helper_failure_contracts(hass, entry):
    """Deterministic adapter-fault supplement; auth/TLS are proven separately."""
    from unittest.mock import AsyncMock, patch
    from types import SimpleNamespace
    from multidict import MultiDict
    from homeassistant.components import http
    from homeassistant.components.http import KEY_HASS_USER
    from homeassistant.exceptions import ConfigEntryError
    component=__import__('custom_components.'+DOMAIN,fromlist=['async_setup_entry'])
    flows=__import__('custom_components.'+DOMAIN+'.config_flow',fromlist=['NativeTrialFlow'])
    bridge=__import__('custom_components.'+DOMAIN+'.bridge',fromlist=['BridgeError'])
    old=dict(entry.data)
    def flow():
        f=flows.NativeTrialFlow();f.hass=hass;f.flow_id=secrets.token_hex(16)
        f.entry=entry;f.actor=old['actor'];f.binding=dict(old['binding']);f.staged=True
        f.retirement_actor=old['actor'];return f
    # Missing/corrupted Core identity must fail closed on actual setup.
    keys=flows.CoreKeys(Path(hass.config.path('.storage',DOMAIN,old['installation'])))
    raw=keys.path if hasattr(keys,'path') else None
    key_path=Path(hass.config.path('.storage',DOMAIN,old['installation'],'core.key'))
    original_key=key_path.read_bytes()
    key_path.write_bytes(b'invalid-synthetic-key')
    try:
        try: await component.async_setup_entry(hass,entry)
        except ConfigEntryError: pass
        else: raise AssertionError('corrupted_core_key_loaded')
    finally: key_path.write_bytes(original_key)
    # Reference-only retired receipts load without reopening a removed key.
    hass.config_entries.async_update_entry(entry,data={**old,'retired':True,'key_cleanup_pending':False})
    assert await component.async_setup_entry(hass,entry)
    hass.config_entries.async_update_entry(entry,data=old)
    for step in ('connect','confirm','refresh','retire'):
        f=flow()
        result=await getattr(f,'async_step_'+step)({'confirm':False})
        assert result['type']=='form'
        with patch.object(f,'action',AsyncMock(side_effect=bridge.BridgeError())):
            if step!='retire':
                result=await getattr(f,'async_step_'+step)({'confirm':True})
                assert result['type']=='form' and result['errors']
    # Lost acknowledgement: safe status lookup, exactly one mutation admission.
    for step,phase in (('confirm','active'),('refresh','verified')):
        f=flow();port=SimpleNamespace(call=AsyncMock(side_effect=bridge.BridgeError()))
        with patch.object(f,'action',AsyncMock()),patch.object(f,'bridge',return_value=port),patch.object(f,'status',AsyncMock(return_value={'phase':phase})):
            result=await getattr(f,'async_step_'+step)({'confirm':True})
            assert result['reason']==('oauth_active' if step=='confirm' else 'trial_verified')
            assert port.call.await_count==1
    # Unknown status is reported unavailable, without a retry.
    for step in ('confirm','refresh'):
        f=flow();port=SimpleNamespace(call=AsyncMock(side_effect=bridge.BridgeError()))
        with patch.object(f,'action',AsyncMock()),patch.object(f,'bridge',return_value=port),patch.object(f,'status',AsyncMock(side_effect=bridge.BridgeError())):
            assert (await getattr(f,'async_step_'+step)({'confirm':True}))['reason']=='trial_unavailable'
            assert port.call.await_count==1
    f=flow();f.staged=False
    with patch.object(f,'action',AsyncMock()):
        assert (await f.async_step_confirm({'confirm':True}))['reason']=='trial_unavailable'
    f=flow()
    with patch.object(f,'action',AsyncMock()),patch.object(f,'status',AsyncMock(return_value={'phase':'uncertain'})):
        assert (await f.async_step_connect({'confirm':True}))['reason']=='trial_unavailable'
    # Signed callback transport errors can only stage or return unavailable.
    request=SimpleNamespace(path='/auth/external/callback',method='GET',query=MultiDict({'state':'synthetic-state','code':'synthetic-package-code'}))
    for phase in ('staged','uncertain'):
        f=flow();port=SimpleNamespace(call=AsyncMock(side_effect=bridge.BridgeError()))
        value={'state':{'flow_id':f.flow_id,'redirect_uri':bridge.REDIRECT},'code':'synthetic-package-code'}
        with patch.object(flows.http,'current_request',SimpleNamespace(get=lambda:request)),patch.object(flows,'mark_request'),patch.object(f,'bridge',return_value=port),patch.object(f,'status',AsyncMock(return_value={'phase':phase})):
            result=await f.async_step_auth(value)
            assert result['type']==('external_done' if phase=='staged' else 'abort')
            assert port.call.await_count==1
    request=SimpleNamespace(path='/auth/external/callback',method='GET',query=MultiDict({'state':'synthetic-state','error':'access_denied'}))
    f=flow();port=SimpleNamespace(call=AsyncMock(return_value={'phase':'denied'}))
    with patch.object(flows.http,'current_request',SimpleNamespace(get=lambda:request)),patch.object(flows,'mark_request'),patch.object(f,'bridge',return_value=port):
        assert (await f.async_step_auth({'state':{'flow_id':f.flow_id,'redirect_uri':bridge.REDIRECT},'error':'access_denied'}))['reason']=='consent_denied'
    f=flow();f.url='https://accounts.spotify.com/authorize'
    assert (await f.async_step_auth())['type']=='external'
    # Retirement never claims success on an unknown App outcome.
    for outcome in ({'phase':'active'},bridge.BridgeError()):
        f=flow();call=AsyncMock(side_effect=outcome) if isinstance(outcome,Exception) else AsyncMock(return_value=outcome)
        with patch.object(flows,'native_action',AsyncMock()),patch.object(f,'bridge',return_value=SimpleNamespace(call=call)):
            assert (await f.async_step_retire({'confirm':True}))['reason']=='retirement_unconfirmed'
    # Missing request cannot grant removal authority, even in a lifecycle hook.
    with patch.object(http,'current_request',SimpleNamespace(get=lambda:None)):
        await component.async_remove_entry(hass,entry)
    # Expired explicit deletion cleans only matching keys, without App authority.
    request={KEY_HASS_USER:SimpleNamespace(id=old['actor'],is_active=True,is_admin=True)}
    class Removal(dict):
        method='DELETE';path='/api/config/config_entries/entry/'+entry.entry_id
    with tempfile.TemporaryDirectory(prefix='native-retirement-') as temp:
        root=Path(temp)/old['installation'];root.mkdir(mode=0o700)
        for name in ('core.key','ca.crt','client.crt'):
            target=root/name;target.write_bytes((keys.root/name).read_bytes());target.chmod(0o600)
        owned=flows.CoreKeys(root);hashes=owned.hashes()
        dummy=SimpleNamespace(entry_id=entry.entry_id,data={k:v for k,v in old.items() if k!='binding'})
        dummy.data.update(deadline=1,material_hashes=hashes)
        fake_hass=SimpleNamespace(config=SimpleNamespace(path=lambda *args:str(root)),async_add_executor_job=hass.async_add_executor_job)
        with patch.object(http,'current_request',SimpleNamespace(get=lambda:Removal(request))):
            await component.async_remove_entry(fake_hass,dummy)
        assert not root.exists()
    # Cache ownership refuses unknown metadata and unsafe cache files.
    with tempfile.TemporaryDirectory(prefix='native-cache-') as temp:
        root=Path(temp)
        with patch.object(component,'__file__',str(root/'__init__.py')):
            component.record_runtime_cache()
            marker=root/'.source-owned.sha256';marker.write_text('wrong-prefix\n')
            component.record_runtime_cache();assert not (root/'.cache-owned.sha256').exists()
            marker.write_text('# SYMPHONIA_NATIVE_OAUTH_TRIAL_SOURCE_V1\n')
            component.record_runtime_cache();assert (root/'.cache-owned.sha256').exists()
            component.record_runtime_cache()
    return True




def shipping_main_campaign(output: Path, coverage_library: Path):
    """Actual image entry module, with read-only coverage instrumentation only."""
    import time
    image='symphonia-native-oauth-trial:lab-20261030'
    details=json.loads(lab_call(['docker','image','inspect',image]).stdout)[0]
    assert details['Config']['Labels']['io.symphonia.validation.owner']==LABEL
    if output.exists() or output.is_symlink():
        raise RuntimeError('fresh_shipping_fixture_output_required')
    output.mkdir(mode=0o777);output.chmod(0o777)
    (output/'.owned').write_text('symphonia-native-shipping-main-lab-v1\n')
    volume='symphonia-native-main32-'+secrets.token_hex(6)
    lab_call(['docker','volume','create','--label','io.symphonia.validation.owner='+LABEL,volume])
    evidence=output/'coverage';evidence.mkdir(mode=0o777);evidence.chmod(0o777)
    common=['docker','run','--read-only','--network','none','--label','io.symphonia.validation.owner='+LABEL,
        '--mount','type=bind,src='+str(evidence)+',dst=/evidence',
        '--mount','type=bind,src='+str(coverage_library)+',dst=/coverage-lib/coverage,readonly',
        '--env','PYTHONPATH=/coverage-lib','--env','COVERAGE_CORE=pytrace','--entrypoint','python']
    arguments=[image,'-m','coverage','run','--branch','--parallel-mode','--include=/app/symphonia_native_oauth_trial/*.py',
        '--data-file=/evidence/.coverage-shipping','-m','symphonia_native_oauth_trial.run']
    def start(*, mounted=True):
        name='symphonia-native-main32-'+secrets.token_hex(4)
        mounts=['--mount','type=volume,src='+volume+',dst=/data'] if mounted else []
        container=lab_call([*common,'--detach','--name',name,*mounts,*arguments]).stdout.decode().strip()
        assert len(container)==64
        return name
    def finish(name, expected):
        code=int(lab_call(['docker','wait',name],timeout=15).stdout)
        log=lab_call(['docker','logs',name]).stdout
        assert code==expected,(code,log.decode()[:150])
        lab_call(['docker','rm',name])
        return log
    identities=[]
    for _ in range(2):
        name=start()
        try:
            for _ in range(60):
                observed=lab_call(['docker','logs',name]);log=observed.stdout+observed.stderr
                if b'trial_ready' in log:break
                time.sleep(.05)
            else:raise AssertionError('shipping_main_not_ready:'+log.decode()[:1500])
            raw=lab_call(['docker','exec',name,'python','-c',"from pathlib import Path; print(Path('/data/native_trial/identity.json').read_text())"]).stdout
            identities.append(json.loads(raw))
            uid=lab_call(['docker','exec',name,'python','-c',"from pathlib import Path; print(next(x for x in Path('/proc/1/status').read_text().splitlines() if x.startswith('Uid:')).split()[1])"]).stdout.decode().strip()
            assert uid=='10001'
            lab_call(['docker','kill','--signal','TERM',name])
            assert b'trial_stopped' in finish(name,0)
        except BaseException:
            lab_call(['docker','kill',name],check=False);lab_call(['docker','rm',name],check=False);raise
    assert identities[0]==identities[1]
    remove="from pathlib import Path; import stat; p=Path('/data/native_trial/oauth_keys/wrapping.key'); s=p.lstat(); assert stat.S_ISREG(s.st_mode) and s.st_uid==10001 and s.st_nlink==1 and s.st_size==32; p.unlink()"
    lab_call(['docker','run','--rm','--network','none','--mount','type=volume,src='+volume+',dst=/data','--entrypoint','python',image,'-c',remove])
    assert json.loads(finish(start(),78))=={'phase':'locked'}
    assert json.loads(finish(start(mounted=False),78))=={'phase':'unavailable'}
    result={'mode':'shipping_main_process_supplement','image_id':details['Id'],'actual_service_uid':10001,'restart_preserves_identity_deadline':True,'missing_key_locked_without_regeneration':True,'read_only_start_failure_closed':True,'provider_calls':0,'boundary':'Network none; coverage module supplied read-only; shipping source unchanged'}
    (output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    owned=json.loads(lab_call(['docker','volume','inspect',volume]).stdout)[0]
    assert owned['Labels']['io.symphonia.validation.owner']==LABEL
    lab_call(['docker','volume','rm',volume])
    return result




def retire_supervisor_artifacts(backup_slug=None):
    """Only an exact current manifest-owned trial; no wildcard deletion."""
    supervisor_guard()
    from tools.stage_native_oauth_trial import APP_FILES,APP,HELPER_FILES,source_manifest,digest
    expected={name:digest((REPO/APP/name).read_bytes()) for name in APP_FILES}
    image=json.loads(lab_call(['docker','exec',CONTAINER,'docker','inspect','homeassistant']).stdout)[0]['Image']
    sidecar=['docker','exec','-i',CONTAINER,'docker','run','--rm','-i','--network','none','--mount','type=bind,src=/mnt/supervisor/apps/local,dst=/stage','--entrypoint','python3',image,'-c']
    script='''from pathlib import Path
import hashlib,json,sys
root=Path('/stage/symphonia_native_oauth_trial');expected=json.loads(sys.stdin.read())
assert root.is_dir() and not root.is_symlink()
assert {p.name for p in root.iterdir()}==set(expected)|{'SHA256SUMS'}
assert (root/'SHA256SUMS').read_text()==''.join(sha+'  '+name+'\\n' for name,sha in expected.items())
for name,sha in expected.items():
 p=root/name;assert p.is_file() and not p.is_symlink() and p.stat().st_nlink==1 and hashlib.sha256(p.read_bytes()).hexdigest()==sha
print('owned')'''
    # This check precedes uninstall/deletion; a modified stage is preserved.
    lab_call([*sidecar,script],data=json.dumps(expected).encode())
    info=lab_ha('apps','info',SLUG)
    if info.get('version') is not None:
        assert info['version']=='0.1.0b1'
        lab_ha('apps','uninstall',SLUG)
    if backup_slug:
        import re
        assert re.fullmatch('[a-f0-9]{8}',backup_slug)
        info=lab_ha('backups','info',backup_slug)
        assert info['name']=='Symphonia-native-trial-synthetic-package32'
        lab_ha('backups','remove',backup_slug)
    # The fixed script rechecks all bytes immediately before unlinking.
    delete=script.replace("print('owned')", "for name in (*expected,'SHA256SUMS'): (root/name).unlink()\nroot.rmdir()\nprint('removed')")
    lab_call([*sidecar,delete],data=json.dumps(expected).encode())
    helper_hash=digest(source_manifest({name:(REPO/'custom_components'/DOMAIN/name).read_bytes() for name in HELPER_FILES}))
    verify="from pathlib import Path;import hashlib; p=Path('/config/custom_components/"+DOMAIN+"/.source-owned.sha256'); assert hashlib.sha256(p.read_bytes()).hexdigest()=='"+helper_hash+"'"
    lab_call(['docker','exec',CONTAINER,'docker','exec','homeassistant','python3','-c',verify])
    cache="import sys;sys.path.insert(0,'/config'); from custom_components.symphonia_native_oauth_trial import record_runtime_cache;record_runtime_cache()"
    # Core may disable bytecode writes: a cleanup probe must not create a cache
    # after the native flow has recorded an intentionally header-only manifest.
    lab_call(['docker','exec',CONTAINER,'docker','exec','homeassistant','python3','-B','-c',cache])
    lab_call(['docker','exec',CONTAINER,'docker','exec','homeassistant','sh','/tmp/symphonia-native-helper-installer.sh','remove','/config'])
    return {'app_uninstalled':True,'owned_stage_removed':True,'helper_removed':True,'backup_removed':bool(backup_slug)}


def run_package_campaign(output: Path):
    """Called only by the explicitly enabled eight-case integration suite."""
    if output.exists() or output.is_symlink():
        raise RuntimeError('fresh_package_campaign_output_required')
    output.mkdir(mode=0o700)
    (output/'.owned').write_text('symphonia-native-package-campaign-v1\n')
    supervisor_guard()
    docker=['docker','run','--rm','--network','none','--read-only','--user','10001:10001','--tmpfs','/tmp:rw,mode=1777',
        '--add-host','local-symphonia-native-oauth-trial:127.0.0.1','--label','io.symphonia.validation.owner='+LABEL,
        '--mount','type=bind,src='+str(REPO)+',dst=/repo,readonly','--workdir','/repo','--entrypoint','python3',CORE,
        'tools/native_oauth_trial_lab.py','--core-fixture']
    core_result=lab_call(docker,timeout=120)
    (output/'core.log').write_bytes(core_result.stdout+core_result.stderr)
    core=json.loads(core_result.stdout.decode().strip().splitlines()[-1])
    assert core['mode']=='isolated_exact_source_package_core' and all(core['results'].values())
    artifacts=stage_supervisor(output/'artifacts')
    lab_ha('apps','install',SLUG)
    channel=supervisor_channel()
    backup=supervisor_backup()
    result={'format':'symphonia-native-package-campaign-v1','artifacts':artifacts,
        'results':{**core['results'],**channel['results'],**backup['results']},
        'core':core,'channel':channel,'backup':backup,
        'owner_ha_used':False,'live_spotify_used':False}
    (output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    result['cleanup']=retire_supervisor_artifacts(backup['backup_slug'])
    (output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=="__main__": main()
