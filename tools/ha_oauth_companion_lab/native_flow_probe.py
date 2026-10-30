"""Synthetic main-reconfigure/callback research; never install on owner HA."""
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import tempfile
import traceback
from urllib.parse import parse_qs, urlsplit

DOMAIN='symphonia_native_flow_research'
FLOW='''
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import http
from homeassistant.components.http import KEY_HASS_USER
from homeassistant.helpers.config_entry_oauth2_flow import LocalOAuth2ImplementationWithPkce, MY_AUTH_CALLBACK_PATH, AUTH_CALLBACK_PATH
DOMAIN="symphonia_native_flow_research"
def actor():
    request=http.current_request.get()
    user=request.get(KEY_HASS_USER) if request is not None else None
    return user.id if user and user.is_active and user.is_admin else None
class Flow(config_entries.ConfigFlow,domain=DOMAIN):
    VERSION=1
    async def async_step_user(self,user_input=None):
        if actor() is None:
            return self.async_abort(reason="missing_current_admin")
        return self.async_create_entry(title="Synthetic safe references",data={"installation":"synthetic-install"})
    async def async_step_reconfigure(self,user_input=None):
        self._get_reconfigure_entry()
        current=actor()
        if current is None:
            return self.async_abort(reason="missing_current_admin")
        if user_input is None:
            self.owner=current
        if current!=self.owner:
            return self.async_abort(reason="wrong_actor")
        if user_input and user_input.get("start") is True:
            impl=LocalOAuth2ImplementationWithPkce(self.hass,DOMAIN,"synthetic-opaque-id", "", "https://accounts.spotify.com/authorize", "https://accounts.spotify.com/api/token")
            assert impl.redirect_uri==MY_AUTH_CALLBACK_PATH
            self.authorize_url=await impl.async_generate_authorize_url(self.flow_id)
            # TEST boundary: synthetic App port retains verifier only in memory.
            self.hass.data[DOMAIN]["verifiers"].append(impl.code_verifier)
            impl.code_verifier=""
            self.staged=False
            return self.async_external_step(step_id="auth",url=self.authorize_url)
        return self.async_show_form(step_id="reconfigure",data_schema=vol.Schema({vol.Required("start",default=False):bool}))
    async def async_step_auth(self,user_input=None):
        if user_input is None:
            return self.async_external_step(step_id="auth",url=self.authorize_url)
        request=http.current_request.get()
        state=user_input.get("state")
        if (request is None or request.path!=AUTH_CALLBACK_PATH or request.method!="GET"
                or not isinstance(state,dict) or set(state)!={"flow_id","redirect_uri"}
                or state.get("flow_id")!=self.flow_id or state.get("redirect_uri")!=MY_AUTH_CALLBACK_PATH
                or set(user_input)!={"code","state"} or user_input.get("code")!=request.query.get("code")):
            self.hass.data[DOMAIN]["forgeries_refused"]+=1
            return self.async_external_step(step_id="auth",url=self.authorize_url)
        self.hass.data[DOMAIN]["callback_path_observed"]=True
        self.hass.data[DOMAIN]["callback_actor_absent"]=actor() is None
        self.hass.data[DOMAIN]["staged"].append(user_input["code"])
        self.staged=True
        return self.async_external_step_done(next_step_id="confirm")
    async def async_step_confirm(self,user_input=None):
        request=http.current_request.get()
        current=actor()
        if user_input is not None:
            if (request is None or request.method!="POST" or request.path!="/api/config/config_entries/flow/"+self.flow_id
                    or current!=self.owner or not self.staged or set(user_input)!={"confirm"} or user_input.get("confirm") is not True):
                self.hass.data[DOMAIN]["confirmations_refused"]+=1
                return self.async_show_form(step_id="confirm",data_schema=vol.Schema({vol.Required("confirm",default=False):bool}),errors={"base":"fresh_same_admin_required"})
            # TEST boundary: admission count is not an actual provider exchange.
            self.hass.data[DOMAIN]["admissions"]+=1
            return self.async_abort(reason="research_complete")
        return self.async_show_form(step_id="confirm",data_schema=vol.Schema({vol.Required("confirm",default=False):bool}))
'''

async def campaign():
    os.environ.clear()
    os.environ['PATH']='/usr/local/bin:/usr/bin:/bin'
    from aiohttp import ClientSession
    from homeassistant import bootstrap,loader
    from homeassistant.auth.const import GROUP_ID_ADMIN,GROUP_ID_USER
    from homeassistant.core import HomeAssistant
    from homeassistant.const import __version__
    from homeassistant.helpers import config_entry_oauth2_flow as oauth
    logging.getLogger().setLevel(logging.CRITICAL)
    results={}
    with tempfile.TemporaryDirectory(prefix='native-flow-') as directory:
        root=Path(directory)
        component=root/'custom_components'/DOMAIN
        component.mkdir(parents=True)
        (component/'manifest.json').write_text(json.dumps({'domain':DOMAIN,'name':'Synthetic native callback research','version':'0.0.0-lab','config_flow':True,'documentation':'https://example.invalid/','requirements':[],'codeowners':[],'iot_class':'local_push'}))
        (component/'__init__.py').write_text('async def async_setup_entry(hass,entry):\n    return True\n')
        (component/'config_flow.py').write_text(FLOW)
        with socket.socket() as selection:
            selection.bind(('127.0.0.1',0));port=selection.getsockname()[1]
        hass=HomeAssistant(directory)
        loader.async_setup(hass)
        hass.config.skip_pip=True
        counters={'verifiers':[],'staged':[],'forgeries_refused':0,'confirmations_refused':0,'admissions':0,'callback_path_observed':False,'callback_actor_absent':False}
        hass.data[DOMAIN]=counters
        trap_calls=[]
        async def trap(*args,**kwargs):
            trap_calls.append('forbidden_default_token_path')
            raise AssertionError('forbidden_default_token_path')
        oauth.LocalOAuth2Implementation.async_resolve_external_data=trap
        oauth.OAuth2Session.async_ensure_token_valid=trap
        tokens=[];users=[]
        try:
            assert await bootstrap.async_from_config_dict({'http':{'server_host':'127.0.0.1','server_port':port},'api':{},'config':{}},hass) is hass
            # TEST boundary: My enabled flag, no My relay/browser is exercised.
            hass.config.components.add('my')
            hass.http.register_view(oauth.OAuth2AuthorizeCallbackView())
            await hass.async_start()
            await hass.auth.async_create_user('Synthetic owner',group_ids=[GROUP_ID_ADMIN])
            for name,group in [('Admin A',GROUP_ID_ADMIN),('Admin B',GROUP_ID_ADMIN),('Ordinary',GROUP_ID_USER)]:
                user=await hass.auth.async_create_user(name,group_ids=[group])
                refresh=await hass.auth.async_create_refresh_token(user,client_id='https://flow.example.invalid')
                users.append(user);tokens.append([hass.auth.async_create_access_token(refresh),refresh])
            endpoint='/api/config/config_entries/flow'
            async with ClientSession() as client:
                async def call(method,path,payload=None,who=None,params=None):
                    headers={} if who is None else {'Authorization':'Bearer '+tokens[who][0]}
                    async with client.request(method,f'http://127.0.0.1:{port}'+path,json=payload,params=params,headers=headers) as response:
                        raw=await response.read()
                        data=json.loads(raw) if response.content_type=='application/json' else {}
                        return response.status,data
                status,_=await call('POST',endpoint,{'handler':DOMAIN})
                results['setup_unauthenticated_denied']=status==401
                status,entry=await call('POST',endpoint,{'handler':DOMAIN},0)
                assert status==200 and entry['type']=='create_entry', ('setup',status,entry.get('type'))
                entries=hass.config_entries.async_entries(DOMAIN)
                assert len(entries)==1 and dict(entries[0].data)=={'installation':'synthetic-install'}
                entry_id=entries[0].entry_id
                results['setup_creates_only_safe_reference_entry']=True
                async def start(who=0):
                    status,flow=await call('POST',endpoint,{'handler':DOMAIN,'entry_id':entry_id},who)
                    assert status==200 and flow.get('step_id')=='reconfigure',('reconfigure',status,flow.get('type'),flow.get('reason'))
                    path=endpoint+'/'+flow['flow_id']
                    status,external=await call('POST',path,{'start':True},who)
                    assert status==200 and external['type']=='external'
                    params=parse_qs(urlsplit(external['url']).query)
                    return path,external,params
                path,external,params=await start()
                results['actual_main_reconfigure_external_step']=True
                results['actual_pkce_uses_s256']=params.get('code_challenge_method')==['S256'] and len(params.get('code_challenge',[''])[0])>40
                results['exact_my_redirect_generated']=params.get('redirect_uri')==[oauth.MY_AUTH_CALLBACK_PATH]
                _,_,second=await start()
                results['per_attempt_verifiers_and_challenges_distinct']=len(set(counters['verifiers']))==2 and params['code_challenge']!=second['code_challenge']
                status,_=await call('GET',oauth.AUTH_CALLBACK_PATH,params={'state':'invalid-synthetic-signature','code':'synthetic'})
                results['invalid_core_state_signature_refused']=status==400 and not counters['staged']
                fake={'state':{'flow_id':external['flow_id'],'redirect_uri':oauth.MY_AUTH_CALLBACK_PATH},'code':'synthetic-forged-code'}
                await call('POST',path,fake,0)
                results['lookalike_state_direct_flow_post_refused']=counters['forgeries_refused']==1 and not counters['staged']
                canary=secrets.token_urlsafe(48)
                status,_=await call('GET',oauth.AUTH_CALLBACK_PATH,params={'state':params['state'][0],'code':canary})
                results['real_callback_route_stages_matching_state']=status==200 and counters['staged']==[canary] and counters['callback_path_observed']
                results['public_callback_has_no_admin_authority']=counters['callback_actor_absent'] and counters['admissions']==0
                status,step=await call('GET',path,who=0)
                results['native_flow_resumes_to_confirmation_form']=status==200 and step.get('step_id')=='confirm' and counters['admissions']==0
                await call('GET',oauth.AUTH_CALLBACK_PATH,params={'state':params['state'][0],'code':canary})
                results['duplicate_callback_cannot_confirm_or_restage']=counters['staged']==[canary] and counters['admissions']==0
                status,_=await call('POST',path,{'confirm':True})
                results['completion_unauthenticated_denied']=status==401
                status,denied=await call('POST',path,{'confirm':True},2)
                ordinary_status=status
                results['completion_ordinary_user_denied']=(status in (401,403) or status==200 and denied.get('errors',{}).get('base')=='fresh_same_admin_required') and counters['admissions']==0
                status,step=await call('POST',path,{'confirm':True},1)
                results['completion_different_admin_denied']=status==200 and step.get('errors',{}).get('base')=='fresh_same_admin_required' and counters['admissions']==0
                await hass.auth.async_update_user(users[0],is_active=False)
                status,_=await call('POST',path,{'confirm':True},0)
                results['completion_disabled_admin_denied']=status==401
                await hass.auth.async_update_user(users[0],is_active=True)
                hass.auth.async_remove_refresh_token(tokens[0][1])
                status,_=await call('POST',path,{'confirm':True},0)
                results['completion_revoked_login_denied']=status==401
                refresh=await hass.auth.async_create_refresh_token(users[0],client_id='https://flow.example.invalid')
                tokens[0]=[hass.auth.async_create_access_token(refresh),refresh]
                status,step=await call('POST',path,{'confirm':True},0)
                results['fresh_same_admin_native_post_admits_once']=status==200 and step.get('reason')=='research_complete' and counters['admissions']==1
                status,_=await call('POST',path,{'confirm':True},0)
                results['completed_flow_cannot_admit_twice']=status in (400,404) and counters['admissions']==1
                results['default_core_token_paths_never_called']=not trap_calls
                for flow in list(hass.config_entries.flow.async_progress()):
                    hass.config_entries.flow.async_abort(flow['flow_id'])
                await hass.async_block_till_done()
                results['core_entry_retains_only_safe_references']=len(hass.config_entries.async_entries(DOMAIN))==1 and dict(entries[0].data)=={'installation':'synthetic-install'}
                results['synthetic_code_verifiers_absent_from_saved_files']=all(canary.encode() not in file.read_bytes() and all(value.encode() not in file.read_bytes() for value in counters['verifiers']) for file in root.rglob('*') if file.is_file())
            assert all(results.values()), [name for name,value in results.items() if not value]
            return {'mode':'real_core_main_reconfigure_callback_research','core':__version__,'results':results,'ordinary_user_http_status':ordinary_status,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'boundaries':{'my_enabled_flag':'test fixture; actual My relay/browser untested','app_stage_and_admission':'in-memory test port; no TLS/provider/grant','default_token_paths':'explicit traps','owner_ha':'not used','final_package_cases':'zero'}}
        finally:
            await hass.async_stop()

if __name__=='__main__':
    try:
        print(json.dumps(asyncio.run(campaign()),sort_keys=True))
    except BaseException as error:
        print(json.dumps({'mode':'native_flow_probe_failed','exception_type':type(error).__name__,'safe_detail':str(error) if isinstance(error,AssertionError) else None,'locations':[{'file':Path(x.filename).name,'line':x.lineno,'function':x.name} for x in traceback.extract_tb(error.__traceback__)]},sort_keys=True))
        raise SystemExit(1) from None
