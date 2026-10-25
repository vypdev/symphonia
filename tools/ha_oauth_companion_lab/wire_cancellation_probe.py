"""Actual asyncio cancellation of the wire harness with explicit fake HA APIs.

Run in the pinned networkless Core image; no live configuration or real token.
This is harness lifecycle evidence, not another native authorization proof.
"""
import asyncio
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

from tools.ha_oauth_companion_lab.wire_core_fixture import exercise


async def campaign():
    os.environ.clear()
    os.environ['SUPERVISOR_TOKEN']='synthetic-not-a-live-token'
    started=asyncio.Event();removed=[];created=[]
    class Auth:
        async def async_get_users(self):
            return [SimpleNamespace(is_owner=True,is_active=True)]
        async def async_create_user(self,name,*,group_ids):
            user=SimpleNamespace(id='a'*32,name=name)
            created.append(user);return user
        async def async_create_refresh_token(self,*args,**kwargs):
            started.set();await asyncio.Event().wait()
        async def async_remove_user(self,user):
            assert user in created;removed.append(user)
    async def idle():pass
    hass=SimpleNamespace(auth=Auth(),data={},config_entries=SimpleNamespace(
        flow=SimpleNamespace(async_progress_by_handler=lambda domain:[])),async_block_till_done=idle)
    with tempfile.TemporaryDirectory(prefix='symphonia-cancellation-') as directory:
        root=Path(directory)
        task=asyncio.create_task(exercise(hass,root))
        await asyncio.wait_for(started.wait(),5)
        task.cancel();propagated=False
        try:await task
        except asyncio.CancelledError:propagated=True
        receipt=json.loads((root/'receipt.json').read_bytes())
        phase=json.loads((root/'phase.json').read_bytes())
        results={'actual_task_cancellation_propagated':propagated,
            'cancelled_receipt_is_not_success':receipt['error_type']=='CancelledError',
            'cancelled_phase_is_failed':phase=={'phase':'failed','error_type':'CancelledError'},
            'only_created_fake_user_removed':len(removed)==len(created)==receipt['synthetic_users_removed']==1,
            'incomplete_observations_not_claimed':receipt['results']=={},
            'no_provider_or_owner_claim':receipt['real_provider_or_owner_ha'] is False}
        assert all(results.values())
        return {'mode':'actual_asyncio_cancellation_with_fake_ha_apis','results':results,
            'core_dependencies':receipt['core'],'network':'none','native_authentication':'not_exercised'}


if __name__=='__main__':
    print(json.dumps(asyncio.run(campaign()),sort_keys=True))
