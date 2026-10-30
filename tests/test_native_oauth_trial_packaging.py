"""Eight opt-in cases execute exact artifacts against pinned Core/Supervisor.

Ordinary verification skips this privileged laboratory campaign. It never treats
stored receipts or source inspection as execution of the eight package cases.
Run with SYMPHONIA_NATIVE_TRIAL_PACKAGE_LAB=1 and a fresh output path after
preparing the guarded disposable Supervisor. The suite stages, installs,
backs up, restores and retires only its distinct trial artifacts.
"""
import os
import json
from pathlib import Path
import tempfile
import secrets
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


def campaign_failure_cleanup_contracts(case):
    """Injected acquisition failures; actual Supervisor ownership is separate."""
    from tools import native_oauth_trial_lab as lab
    scenarios=('stage_unacquired','stage_acquired','install','channel_before_helper',
               'channel_after_helper','backup_unconfirmed','backup_acquired','cleanup_failure')
    observed=[]
    with tempfile.TemporaryDirectory() as directory:
        for scenario in scenarios:
            output=Path(directory)/scenario
            core={'mode':'isolated_exact_source_package_core','results':{'fixture':True}}
            call=SimpleNamespace(stdout=json.dumps(core).encode(),stderr=b'')
            def stage(path,on_acquired):
                if scenario=='stage_unacquired': raise RuntimeError('injected stage refusal')
                on_acquired()
                if scenario=='stage_acquired': raise RuntimeError('injected copy failure')
                return {'fixture':'acquired stage'}
            def install(*args):
                if scenario=='install': raise RuntimeError('injected install failure')
            def channel(on_helper_acquired):
                if scenario=='channel_before_helper': raise RuntimeError('injected pre-helper failure')
                on_helper_acquired()
                if scenario in ('channel_after_helper','cleanup_failure'): raise RuntimeError('injected channel failure')
                return {'results':{'fixture':True}}
            def backup(on_created):
                if scenario=='backup_unconfirmed': raise RuntimeError('injected lost backup acknowledgement')
                on_created('abcdef12')
                raise RuntimeError('injected backup inspection failure')
            with case.subTest(scenario=scenario), patch.object(lab,'supervisor_guard'), \
                 patch.object(lab,'lab_call',return_value=call),patch.object(lab,'stage_supervisor',side_effect=stage), \
                 patch.object(lab,'lab_ha',side_effect=install),patch.object(lab,'supervisor_channel',side_effect=channel), \
                 patch.object(lab,'supervisor_backup',side_effect=backup), \
                 patch.object(lab,'retire_supervisor_artifacts',return_value={'fixture_cleanup':True}) as cleanup:
                if scenario=='cleanup_failure': cleanup.side_effect=ValueError('preserve modified fixture')
                with case.assertRaises(RuntimeError) as raised:
                    lab.run_package_campaign(output)
                receipt=json.loads((output/'receipt.json').read_text())
                case.assertFalse(receipt['completed'])
                if scenario=='stage_unacquired': cleanup.assert_not_called()
                else:
                    case.assertEqual(1,cleanup.call_count)
                    case.assertEqual('abcdef12' if scenario=='backup_acquired' else None,cleanup.call_args.args[0])
                    case.assertEqual(scenario!='stage_acquired',cleanup.call_args.kwargs['remove_app'])
                    case.assertEqual(scenario in ('channel_after_helper','backup_unconfirmed','backup_acquired','cleanup_failure'),cleanup.call_args.kwargs['remove_helper'])
                if scenario=='backup_unconfirmed': case.assertTrue(receipt['backup_acquisition_unconfirmed'])
                if scenario=='cleanup_failure':
                    case.assertEqual('ValueError',receipt['cleanup_error_type'])
                    case.assertTrue(raised.exception.__notes__)
                observed.append({'scenario':scenario,'injected_ports':True,'completed':False})
        for code,stderr in ((125,b'docker unavailable'),(1,b'container not running')):
            acquired=Mock()
            response=SimpleNamespace(returncode=code,stdout=b'',stderr=stderr)
            with case.subTest(absence_error=code),patch.object(lab,'supervisor_guard'), \
                 patch('tools.stage_native_oauth_trial.stage',return_value={}), \
                 patch.object(lab,'lab_call',return_value=response) as calls:
                with case.assertRaises(RuntimeError):
                    lab.stage_supervisor(Path(directory)/('absence-'+str(code)),on_acquired=acquired)
                acquired.assert_not_called()
                case.assertEqual(1,calls.call_count)
    return observed


def shipping_failure_cleanup_contracts(case):
    """Real Docker failure cleanup; mocked foreign metadata is labeled separately."""
    from tools import native_oauth_trial_lab as lab
    image=json.loads(lab.lab_call(['docker','image','inspect',lab.CORE]).stdout)[0]['Id']
    observed=[]
    for with_container in (False,True):
        volume='symphonia-native-main32-'+secrets.token_hex(6)
        name='symphonia-native-main32-'+secrets.token_hex(4)
        with case.subTest(real_shipping_failure=with_container),case.assertRaisesRegex(RuntimeError,'injected shipping failure'):
            with lab.shipping_resources(volume,image) as claim:
                if with_container:
                    claim(name)
                    lab.lab_call(['docker','run','--detach','--name',name,'--label','io.symphonia.validation.owner='+lab.LABEL,
                                  '--network','none','--read-only','--mount','type=volume,src='+volume+',dst=/data',
                                  '--entrypoint','python3',image,'-c','import time; time.sleep(30)'])
                raise RuntimeError('injected shipping failure')
        case.assertFalse(lab.shipping_object_exists('volume',volume))
        case.assertFalse(lab.shipping_object_exists('container',name))
        observed.append({'real_docker':True,'container_acquired':with_container,'resources_removed':True})
    foreign={'Name':'/symphonia-native-main32-aaaaaaaa','Image':image,
             'Config':{'Labels':{'io.symphonia.validation.owner':'unrelated'}},'State':{'Running':True}}
    with patch.object(lab,'shipping_object_exists',return_value=True), \
         patch.object(lab,'lab_call',return_value=SimpleNamespace(stdout=json.dumps([foreign]).encode())) as calls:
        with case.assertRaises(AssertionError): lab.remove_shipping_container('symphonia-native-main32-aaaaaaaa',image)
        case.assertEqual(1,calls.call_count)  # Metadata inspected; no kill/unlink.
    return observed


@unittest.skipUnless(os.environ.get("SYMPHONIA_NATIVE_TRIAL_PACKAGE_LAB") == "1",
                     "requires explicit pinned disposable Supervisor package campaign")
class NativeTrialPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.native_oauth_trial_lab import run_package_campaign
        value=os.environ.get("SYMPHONIA_NATIVE_TRIAL_PACKAGE_OUTPUT")
        if not value or not Path(value).is_absolute():
            raise RuntimeError("fresh_absolute_package_output_required")
        cls.receipt=run_package_campaign(Path(value))

    def test_package_C01_actual_core_actors(self):
        self.assertTrue(self.receipt["results"]["package_C01_real_core_actor_guards"])
        self.assertEqual("2026.10.4", self.receipt["core"]["core"])

    def test_package_C02_actual_callback_stages_without_exchange(self):
        self.assertTrue(self.receipt["results"]["package_C02_real_core_callback_stages_only"])
        self.assertFalse(self.receipt["live_spotify_used"])

    def test_package_C03_actual_supervisor_alias_csr_mtls(self):
        self.assertTrue(self.receipt["results"]["package_C03_actual_supervisor_alias_csr_mtls"])
        self.assertTrue(all(self.receipt["channel"]["channel"].values()))
        self.assertEqual(10001, self.receipt["channel"]["service_uid"])
        self.assertFalse(self.receipt["channel"]["host_ports"])

    def test_package_C04_offline_native_tls_grant_composition(self):
        self.assertTrue(self.receipt["results"]["package_C04_same_source_native_tls_sealed_grant"])
        self.assertFalse(self.receipt["owner_ha_used"])

    def test_package_C05_actual_app_process_restart_refresh(self):
        self.assertTrue(self.receipt["results"]["package_C05_process_restart_confirmed_refresh"])
        self.assertEqual("actual child process", self.receipt["core"]["boundaries"]["app_restart"])

    def test_package_C06_actual_backup_locked_restore(self):
        self.assertTrue(self.receipt["results"]["package_C06_real_supervisor_backup_locked_restore"])
        self.assertEqual(0,self.receipt["backup"]["archive"]["key_files"])
        self.assertFalse(self.receipt["backup"]["keys_regenerated"])
        self.assertEqual(78,self.receipt["backup"]["shipping_main_exit"])

    def test_package_C07_exact_owned_installer_rollback(self):
        self.assertTrue(self.receipt["results"]["package_C07_hash_installer_owned_rollback"])
        self.assertTrue(all(self.receipt["cleanup"].values()))
        self.assertTrue(self.receipt['core']['results']['installer_signals_stop_without_false_success_or_further_unlink'])
        observed=campaign_failure_cleanup_contracts(self)
        path=Path(os.environ['SYMPHONIA_NATIVE_TRIAL_PACKAGE_OUTPUT'])/'failure-cleanup-contracts.json'
        path.write_text(json.dumps(observed,indent=2)+'\n')
        shipping=shipping_failure_cleanup_contracts(self)
        (path.parent/'shipping-failure-contracts.json').write_text(json.dumps(shipping,indent=2)+'\n')

    def test_package_C08_original_deadline_and_retirement(self):
        self.assertTrue(self.receipt["results"]["package_C08_deadline_retire_no_rebootstrap"])
        self.assertTrue(self.receipt["backup"]["same_original_deadline"])
