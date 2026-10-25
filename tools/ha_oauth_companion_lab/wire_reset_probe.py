"""Actual child death between credential reset commit and pair revocation.

Only a fresh owned /data/wire-reset-lab as UID10001; no provider/native actor
claim. Native admission and real Supervisor wire are independent experiments.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from tools.ha_oauth_companion_lab.enrollment_probe import Issuer,client,crypto
from tools.ha_oauth_companion_lab.key_custody_probe import PrivateFiles,encoded
from tools.ha_oauth_companion_lab.wire_app import server
from tools.ha_oauth_companion_lab.recovery_probe import RecoveryVault

BASE=Path('/data/wire-reset-lab')
MARKER='symphonia-wire-reset-crash-v1'


def child():
    assert os.geteuid()==10001
    with PrivateFiles(BASE) as files:
        assert json.loads(files.read('owned.json'))=={'marker':MARKER}
    server.ROOT=BASE/'app'
    state=server.State()
    _,csr=client()
    _,certificate=state.issuer.enroll(state.challenge,csr)
    x509,_,serialization,*_=crypto()
    der=x509.load_pem_x509_certificate(certificate.encode()).public_bytes(serialization.Encoding.DER)
    with PrivateFiles(BASE) as files:
        files.publish('old-public.der',der,exclusive=True)
    def checkpoint(point):
        if point=='reset_after_commit':
            os._exit(84)  # No finally, no pair revoke, no normal process teardown.
    state.vault.explicit_reset(test_authorized=True,checkpoint=checkpoint)
    raise AssertionError('expected_real_process_death')


def campaign():
    assert os.geteuid()==10001 and not BASE.exists() and not BASE.is_symlink()
    BASE.mkdir(mode=0o700)
    with PrivateFiles(BASE) as files:
        files.publish('owned.json',encoded({'marker':MARKER}),exclusive=True)
    result=subprocess.run([sys.executable,__file__,'child'],capture_output=True,timeout=15)
    assert result.returncode==84
    server.ROOT=BASE/'app'
    with PrivateFiles(BASE) as files:
        der=files.read('old-public.der',8192)
    active=RecoveryVault(server.ROOT/'grants');active_key=active.snapshot()[1];active.close()
    keys=[server.ROOT/'issuer/ca.key',server.ROOT/'issuer/server.key',server.ROOT/'grants/keys'/active_key]
    before={p:hashlib.sha256(p.read_bytes()).digest() for p in keys}
    state=server.State()
    results={'actual_reset_commit_process_death':True,
        'completed_reset_phase_survives':state.vault.phase()=='unpaired',
        'startup_never_reopens_tls_authority':state.issuer is None,
        'startup_never_rearms_challenge':state.challenge is None,
        'public_pair_unavailable_before_listener':state.public_signer() is None,
        'history_retained':state.vault.db.execute('SELECT value FROM history').fetchone()[0]=='retained-synthetic-history'}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as executor:
        results['tls_worker_uses_independent_connection_and_denies_reset']=executor.submit(state.tls_active).result(timeout=3) is False
    state.vault.close()
    again=server.State()
    issuer=Issuer(server.ROOT/'issuer')
    results['revocation_is_idempotent_and_old_certificate_denied']=not issuer.accepts(der) and issuer.db.execute('SELECT epoch,serial,peer FROM pair').fetchone()==(1,None,None)
    issuer.close()
    results['no_private_key_replaced_or_added']=set((server.ROOT/'grants/keys').iterdir())==set(keys[2:]) and all(hashlib.sha256(p.read_bytes()).digest()==digest for p,digest in before.items())
    results['obsolete_grant_files_and_keys_retired']=not list((server.ROOT/'grants/records').iterdir()) and not again.vault.reset_retirement_pending()
    again.vault.close()
    assert all(results.values())
    import cryptography,platform
    return {'mode':'synthetic_actual_death_before_pair_revocation','uid':os.geteuid(),
        'python':platform.python_version(),'cryptography':cryptography.__version__,
        'native_reset_admission':'explicit_test_stub; separately proved on real native HTTP',
        'results':results}


if __name__=='__main__':
    if sys.argv[1:]==['child']:child()
    else:print(json.dumps(campaign(),sort_keys=True))
