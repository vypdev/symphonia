"""Eight opt-in cases execute exact artifacts against pinned Core/Supervisor.

Ordinary verification skips this privileged laboratory campaign. It never treats
stored receipts or source inspection as execution of the eight package cases.
Run with SYMPHONIA_NATIVE_TRIAL_PACKAGE_LAB=1 and a fresh output path after
preparing the guarded disposable Supervisor. The suite stages, installs,
backs up, restores and retires only its distinct trial artifacts.
"""
import os
from pathlib import Path
import unittest


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

    def test_package_C08_original_deadline_and_retirement(self):
        self.assertTrue(self.receipt["results"]["package_C08_deadline_retire_no_rebootstrap"])
        self.assertTrue(self.receipt["backup"]["same_original_deadline"])
