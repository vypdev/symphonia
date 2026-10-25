"""Explicit opt-in operator for the pinned disposable HA laboratory.

Never run against an owner installation. Commands fence exact lab/Core identity,
source hashes and ownership; cleanup refuses unexpected configuration changes.
Receipts exclude cookies, URLs, approvals, grants and private keys.
"""
from pathlib import Path
import base64
import hashlib
import json
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[2]
OUT=None
CONTAINER='symphonia-ha-lab'
CORE='sha256:dd1ad589936601cacb1b4797d17e27ce762b5147fb46b0e8e3d5486ab95e56c3'
IMAGE='ghcr.io/home-assistant/qemuarm-64-homeassistant@sha256:dd1ad589936601cacb1b4797d17e27ce762b5147fb46b0e8e3d5486ab95e56c3'
APP='symphonia_oauth_recovery_wire'
SLUG='local_'+APP
DOMAIN='symphonia_native_reset_research'
CORE_ROOT='/config/.symphonia-wire-lab-v1'

def call(args,*,data=None,check=True,timeout=600):
    p=subprocess.run(args,input=data,capture_output=True,timeout=timeout)
    if check and p.returncode:
        raise RuntimeError('guarded_lab_command_failed_'+str(p.returncode))
    return p

def guard():
    sys.path.insert(0,str(REPO))
    from tools.ha_app_lab import _container_details,_is_lab_container
    details=_container_details()
    assert details and _is_lab_container(details) and details['running']=='true'
    p=call(['docker','exec',CONTAINER,'docker','inspect','homeassistant','--format','{{.Image}}'])
    assert p.stdout.decode().strip()==CORE

def sidecar(bind,script,value=None):
    data=json.dumps(value or {}).encode()
    p=call(['docker','exec','-i',CONTAINER,'docker','run','--rm','-i','--network','none',
        '--mount','type=bind,src='+bind+',dst=/stage','--entrypoint','python3',IMAGE,'-c',script],data=data)
    return json.loads(p.stdout)

def core(script):
    p=call(['docker','exec',CONTAINER,'docker','exec','homeassistant','python3','-c',script])
    return json.loads(p.stdout)

def ha(*args,check=True):
    p=call(['docker','exec',CONTAINER,'ha',*args,'--raw-json'],check=False)
    if p.returncode:
        if check: raise RuntimeError('guarded_ha_operation_failed')
        return None
    x=json.loads(p.stdout)
    if x.get('result')!='ok':
        if check: raise RuntimeError('guarded_ha_result_failed')
        return None
    return x.get('data')

def phase():
    return core("from pathlib import Path; import json; p=Path('"+CORE_ROOT+"/phase.json'); print(p.read_text() if p.exists() else json.dumps({'phase':'waiting'}))")

def stage():
    common=['tools/__init__.py','tools/ha_oauth_companion_lab/key_custody_probe.py',
        'tools/ha_oauth_companion_lab/key_publication_probe.py','tools/ha_oauth_companion_lab/recovery_probe.py',
        'tools/ha_oauth_companion_lab/enrollment_probe.py','tools/ha_oauth_companion_lab/native_reset_probe.py',
        'tools/ha_oauth_companion_lab/app/server.py']
    appfiles={p:(REPO/p).read_bytes() for p in common+['tools/ha_oauth_companion_lab/wire_app/server.py']}
    appfiles['Dockerfile']=(REPO/'tools/ha_oauth_companion_lab/wire_app/Dockerfile').read_bytes()
    appfiles['config.yaml']=(REPO/'tools/ha_oauth_companion_lab/wire_app/app-metadata.fixture.json').read_bytes()
    script=r'''
from pathlib import Path,PurePosixPath
import base64,hashlib,json,os,sys
x=json.load(sys.stdin);root=Path('/stage')/x['directory']
assert not root.exists() and not root.is_symlink()
root.mkdir(mode=0o755)
manifest={}
for name,encoded in x['files'].items():
    parts=PurePosixPath(name).parts
    assert parts and not name.startswith('/') and all(p not in {'.','..'} for p in parts)
    data=base64.b64decode(encoded,validate=True);assert len(data)<=262144
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
    for parent in target.parents:
        if parent==root.parent: break
        parent.chmod(0o755)
    with target.open('xb') as output: output.write(data)
    target.chmod(0o644);manifest[name]=hashlib.sha256(data).hexdigest()
(root/'.owned-stage.json').write_text(json.dumps({'marker':'symphonia-owned-wire-stage-v1','files':manifest}))
print(json.dumps({'staged':True,'files':manifest}))
'''
    app=sidecar('/mnt/supervisor/apps/local',script,{'directory':APP,'files':{k:base64.b64encode(v).decode() for k,v in appfiles.items()}})
    from tools.ha_oauth_companion_lab.native_reset_probe import FLOW_SOURCE
    prefix='custom_components.'+DOMAIN+'._research.tools.'
    shim="""from pathlib import Path
import json,os,sys
async def async_setup(hass,config):
    from homeassistant.const import __version__
    root=Path(hass.config.config_dir)/'.symphonia-wire-lab-v1'
    if root.is_dir():
        value={'generic_tools_already_loaded':'tools' in sys.modules,'core':__version__,'uid':os.geteuid()}
        target=root/'setup-diagnostic.json';target.write_text(json.dumps(value));target.chmod(0o600)
    from ._research.tools.ha_oauth_companion_lab.wire_core_fixture import async_setup as setup
    return await setup(hass,config)
"""
    component={'__init__.py':shim.encode(),'config_flow.py':FLOW_SOURCE.replace('from tools.','from '+prefix).encode(),'_research/__init__.py':b'',
        'manifest.json':json.dumps({'domain':DOMAIN,'name':'Disposable native recovery wire probe','version':'0.0.0-lab.1',
            'config_flow':True,'documentation':'https://github.com/vypdev/symphonia','codeowners':[],
            'requirements':[],'dependencies':['http','api','config','hassio'],'iot_class':'local_push'}).encode()}
    for p in common+['tools/ha_oauth_companion_lab/wire_core_fixture.py']:
        component['_research/'+p]=(REPO/p).read_text().replace('from tools.','from '+prefix).encode()
    script=r'''
from pathlib import Path,PurePosixPath
import base64,hashlib,json,os,stat,sys
x=json.load(sys.stdin);base=Path('/stage');component=base/'custom_components'/x['domain'];root=base/'.symphonia-wire-lab-v1'
assert not root.exists() and not root.is_symlink() and not component.exists() and not component.is_symlink()
parent=component.parent
assert not parent.is_symlink()
parent.mkdir(exist_ok=True)
config=base/'configuration.yaml';info=config.lstat();assert stat.S_ISREG(info.st_mode) and info.st_nlink==1
original=config.read_bytes();assert len(original)<=131072 and x['domain'].encode()+b':' not in original
modified=original+b'\n'+x['domain'].encode()+b':\n'
root.mkdir(mode=0o700);component.mkdir(mode=0o755)
backup=root/'configuration.original';backup.write_bytes(original);backup.chmod(0o600)
manifest={}
for name,value in x['files'].items():
    parts=PurePosixPath(name).parts;assert parts and not name.startswith('/') and all(p not in {'.','..'} for p in parts)
    data=base64.b64decode(value,validate=True);target=component/name;target.parent.mkdir(parents=True,exist_ok=True)
    for p in target.parents:
        if p==component.parent: break
        p.chmod(0o755)
    with target.open('xb') as f: f.write(data)
    target.chmod(0o644);manifest[name]=hashlib.sha256(data).hexdigest()
marker={'marker':'symphonia-core-wire-approval-v1','files':manifest,'config_before':hashlib.sha256(original).hexdigest(),
    'config_after':hashlib.sha256(modified).hexdigest(),'original_mode':stat.S_IMODE(info.st_mode)}
(root/'owned.json').write_text(json.dumps(marker));(root/'owned.json').chmod(0o600)
temporary=base/'.symphonia-configuration.pending'
with temporary.open('xb') as f: f.write(modified);f.flush();os.fsync(f.fileno())
temporary.chmod(stat.S_IMODE(info.st_mode));os.replace(temporary,config)
print(json.dumps({'staged':True,'files':manifest,'config_before':marker['config_before'],'config_after':marker['config_after']}))
'''
    component_result=sidecar('/mnt/supervisor/homeassistant',script,{'domain':DOMAIN,'files':{k:base64.b64encode(v).decode() for k,v in component.items()}})
    result={'app':app,'component':component_result,'base_image':IMAGE}
    (OUT/'wire-stage-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'app_files':len(app['files']),'component_files':len(component_result['files']),'staged':True}))

def install():
    ha('store','reload')
    info=ha('apps','info',SLUG)
    assert info.get('version') is None
    ha('apps','install',SLUG)
    ha('apps','start',SLUG,check=False)
    wait_started()
    info=ha('apps','info',SLUG)
    print(json.dumps({'state':info.get('state'),'version':info.get('version')}))

def wait_started():
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        info=ha('apps','info',SLUG,check=False)
        if info and info.get('state')=='started':
            p=call(['docker','exec',CONTAINER,'docker','inspect','app_'+SLUG])
            data=json.loads(p.stdout)[0]
            if data['State'].get('Health',{}).get('Status')=='healthy':
                return
        time.sleep(.5)
    raise RuntimeError('fixture_not_started_and_healthy')

def restart_core():
    ha('core','restart');print(json.dumps({'core_restart_requested':True}))

def lose_keys():
    assert phase().get('phase')=='paired'
    ha('apps','stop',SLUG)
    script=r'''
from pathlib import Path
import json,os,re,sqlite3,stat
r=Path('/stage/wire-lab');assert json.loads((r/'owned.json').read_bytes())['marker']=='symphonia-live-wire-lab-v1'
db=sqlite3.connect('file:'+str(r/'grants/state.sqlite')+'?mode=ro',uri=True)
key=db.execute('SELECT key_ref FROM state').fetchone()[0];db.close();assert re.fullmatch('[a-f0-9]{32}',key)
paths=[r/'issuer/ca.key',r/'issuer/server.key',r/'grants/keys'/key]
for p in paths:
    info=p.lstat();assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==10001 and stat.S_IMODE(info.st_mode)==0o600
for p in paths: p.unlink()
print(json.dumps({'removed_synthetic_private_keys':3}))
'''
    result=sidecar('/mnt/supervisor/apps/data/'+SLUG,script)
    ha('apps','start',SLUG,check=False)
    wait_started()
    script="import sys,json; from pathlib import Path; sys.path.insert(0,'/config/custom_components/"+DOMAIN+"/_research'); from tools.ha_oauth_companion_lab.key_custody_probe import PrivateFiles,encoded; root=Path('"+CORE_ROOT+"'); assert json.loads((root/'owned.json').read_bytes())['marker']=='symphonia-core-wire-approval-v1'; files=PrivateFiles(root); files.publish('continue-after-key-loss.json',encoded({'continue_after_key_loss':True}),exclusive=True); files.__exit__(); print(json.dumps({'continued':True}))"
    result.update(core(script));(OUT/'wire-key-loss-receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

def receipt():
    result=core("from pathlib import Path; p=Path('"+CORE_ROOT+"/receipt.json'); print(p.read_text())")
    assert set(result)<= {'mode','core','cryptography','results','error_type','stage','synthetic_users_removed','no_existing_user_auth_token_read','real_provider_or_owner_ha','browser_cookie_semantics_proven'}
    (OUT/'wire-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

def cleanup():
    p=phase()
    if p.get('phase')=='paired':
        core("import sys,json; from pathlib import Path; sys.path.insert(0,'/config/custom_components/"+DOMAIN+"/_research'); from tools.ha_oauth_companion_lab.key_custody_probe import PrivateFiles,encoded; f=PrivateFiles(Path('"+CORE_ROOT+"')); f.publish('continue-after-key-loss.json',encoded({'abort':True}),exclusive=True); f.__exit__(); print(json.dumps({'abort_sent':True}))")
        for _ in range(30):
            time.sleep(.5);p=phase()
            if p.get('phase') in {'complete','failed'}:break
        assert p.get('phase') in {'complete','failed'}
    info=ha('apps','info',SLUG,check=False)
    if info and info.get('version') is not None:
        ha('apps','uninstall',SLUG)
    # Restore only byte-identical augmented config and our verified component.
    script=r'''
from pathlib import Path
import hashlib,json,os,re,stat
base=Path('/stage');root=base/'.symphonia-wire-lab-v1';component=base/'custom_components/symphonia_native_reset_research'
meta=json.loads((root/'owned.json').read_bytes());assert meta['marker']=='symphonia-core-wire-approval-v1'
config=base/'configuration.yaml';assert hashlib.sha256(config.read_bytes()).hexdigest()==meta['config_after']
original=(root/'configuration.original').read_bytes();assert hashlib.sha256(original).hexdigest()==meta['config_before']
files=[p for p in component.rglob('*') if not p.is_dir()];expected=meta['files'];caches=[]
for p in files:
    assert not p.is_symlink() and stat.S_ISREG(p.lstat().st_mode)
    name=str(p.relative_to(component))
    if name in expected: assert hashlib.sha256(p.read_bytes()).hexdigest()==expected[name]
    else:
        assert p.parent.name=='__pycache__' and re.fullmatch('[A-Za-z_][A-Za-z0-9_]*\\.cpython-314(?:\\.opt-[0-9]+)?\\.pyc',p.name)
        caches.append(p)
assert set(expected)=={str(p.relative_to(component)) for p in files if p not in caches}
temporary=base/'.symphonia-configuration.restore'
with temporary.open('xb') as f:f.write(original);f.flush();os.fsync(f.fileno())
temporary.chmod(meta['original_mode']);os.replace(temporary,config)
for p in files:p.unlink()
for p in sorted([p for p in component.rglob('*') if p.is_dir()],key=lambda p:len(p.parts),reverse=True):p.rmdir()
component.rmdir()
print(json.dumps({'config_restored':True,'component_removed':True,'owned_source_files':len(expected),'owned_cache_files':len(caches)}))
'''
    core_cleanup=sidecar('/mnt/supervisor/homeassistant',script)
    ha('core','restart')
    script=r'''
from pathlib import Path
import json,stat
r=Path('/stage/.symphonia-wire-lab-v1');assert json.loads((r/'owned.json').read_bytes())['marker']=='symphonia-core-wire-approval-v1'
created=json.loads((r/'users.json').read_bytes())['users'] if (r/'users.json').exists() else []
auth=json.loads(Path('/stage/.storage/auth').read_bytes())['data']['users'];ids={u['id'] for u in auth}
assert all(u['id'] not in ids for u in created)
allowed={'owned.json','configuration.original','users.json','phase.json','receipt.json','continue-after-key-loss.json','client.crt','core-keys/core.key','setup-diagnostic.json','failure-diagnostic.json'}
files=[p for p in r.rglob('*') if not p.is_dir()]
assert {str(p.relative_to(r)) for p in files}<=allowed
assert all(stat.S_ISREG(p.lstat().st_mode) and p.stat().st_nlink==1 and p.stat().st_uid==0 and stat.S_IMODE(p.stat().st_mode)==0o600 for p in files)
measure={'owned_private_files':len(files),'allocated_bytes':sum(p.stat().st_blocks*512 for p in files),'synthetic_users_absent':len(created)}
for p in files:p.unlink()
for p in sorted([p for p in r.rglob('*') if p.is_dir()],key=lambda p:len(p.parts),reverse=True):p.rmdir()
r.rmdir();print(json.dumps(measure))
'''
    private_cleanup=sidecar('/mnt/supervisor/homeassistant',script)
    script=r'''
from pathlib import Path
import hashlib,json
r=Path('/stage/symphonia_oauth_recovery_wire');meta=json.loads((r/'.owned-stage.json').read_bytes());assert meta['marker']=='symphonia-owned-wire-stage-v1'
files=[p for p in r.rglob('*') if p.is_file()];expected=meta['files']
assert all(not p.is_symlink() for p in r.rglob('*'))
assert {str(p.relative_to(r)) for p in files}==set(expected)|{'.owned-stage.json'}
for p in files:
    name=str(p.relative_to(r))
    if name in expected:assert hashlib.sha256(p.read_bytes()).hexdigest()==expected[name]
for p in files:p.unlink()
for p in sorted([p for p in r.rglob('*') if p.is_dir()],key=lambda p:len(p.parts),reverse=True):p.rmdir()
r.rmdir();print(json.dumps({'app_source_removed':True,'owned_source_files':len(expected)}))
'''
    app_cleanup=sidecar('/mnt/supervisor/apps/local',script)
    result={'core':core_cleanup,'private':private_cleanup,'app':app_cleanup}
    (OUT/'wire-cleanup-receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':
    import argparse,os,stat
    parser=argparse.ArgumentParser(description="Disposable symphonia-ha-lab only; never owner HA")
    parser.add_argument("command",choices=["stage","install-start","restart-core","phase","lose-keys","receipt","cleanup"])
    parser.add_argument("--receipts",type=Path,required=True)
    args=parser.parse_args()
    OUT=args.receipts.absolute()
    assert OUT==OUT.resolve() and not OUT.is_symlink()
    if not OUT.exists():
        OUT.mkdir(mode=0o700)
        (OUT/".wire-owned.json").write_text(json.dumps({"marker":"symphonia-wire-operator-v1"}))
        (OUT/".wire-owned.json").chmod(0o600)
    info=OUT.lstat()
    assert stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700
    marker=OUT/".wire-owned.json"
    assert not marker.is_symlink() and json.loads(marker.read_bytes())=={"marker":"symphonia-wire-operator-v1"}
    guard()
    command=args.command
    if command=='stage':stage()
    elif command=='install-start':install()
    elif command=='restart-core':restart_core()
    elif command=='phase':print(json.dumps(phase()))
    elif command=='lose-keys':lose_keys()
    elif command=='receipt':receipt()
    elif command=='cleanup':cleanup()
    else:raise SystemExit('unknown bounded operation')
