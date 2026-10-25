import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.prepare_ha_oauth_trial import FILES, prepare


class TrialArtifactTests(unittest.TestCase):
    def test_export_is_deterministic_allowlisted_and_digest_verified(self):
        def show(command, **kwargs):
            self.assertEqual(command[:2], ["git", "show"])
            return SimpleNamespace(stdout=command[2].encode())
        with tempfile.TemporaryDirectory() as directory, patch("tools.prepare_ha_oauth_trial.subprocess.run", side_effect=show):
            first, second = Path(directory) / "one", Path(directory) / "two"
            manifest = prepare("a" * 40, first)
            prepare("a" * 40, second)
            archive = first / "symphonia-oauth-trial.tar.gz"
            self.assertEqual(archive.read_bytes(), (second / archive.name).read_bytes())
            self.assertEqual(manifest["archive_sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
            with tarfile.open(archive) as source:
                self.assertEqual(set(source.getnames()), {"symphonia_oauth_trial/" + name for name in FILES})
                for item in source:
                    self.assertTrue(item.isfile())
                    self.assertEqual(hashlib.sha256(source.extractfile(item).read()).hexdigest(), manifest["files"][Path(item.name).name])
            script = (first / "stage-in-home-assistant.sh").read_text()
            self.assertEqual(script.count("sha256sum -c"), 4)
            self.assertEqual(script.count("https://raw.githubusercontent.com/vypdev/symphonia/" + "a" * 40), 4)
            self.assertIn("test ! -e /addons/symphonia_oauth_trial", script)
            self.assertNotIn("ha apps start", script)
            self.assertEqual(json.loads((first / "manifest.json").read_text()), manifest)

    def test_moving_refs_are_rejected_before_any_source_read(self):
        with patch("tools.prepare_ha_oauth_trial.subprocess.run") as run:
            for revision in ("HEAD", "develop", "a" * 39, "../bad"):
                with self.assertRaises(ValueError):
                    prepare(revision, "/unused")
            run.assert_not_called()

    def test_existing_destination_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory, patch("tools.prepare_ha_oauth_trial.subprocess.run", return_value=SimpleNamespace(stdout=b"fixture")):
            protected = Path(directory) / "authored.txt"
            protected.write_text("retain")
            with self.assertRaises(FileExistsError):
                prepare("a" * 40, directory)
            self.assertEqual(protected.read_text(), "retain")
            self.assertEqual(list(Path(directory).iterdir()), [protected])
