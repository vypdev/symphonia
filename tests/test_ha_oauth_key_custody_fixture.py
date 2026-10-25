"""Offline filesystem safety for the opt-in research fixture, not a vault SDD."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.ha_oauth_companion_lab.key_custody_probe import Locked, PrivateFiles


class LocalKeyFixtureFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)

    def write(self, name="key", content=b"synthetic-key"):
        with PrivateFiles(self.root) as files:
            files.publish(name, content, exclusive=True)

    def test_private_atomic_publication_and_read(self):
        self.write()
        self.assertEqual((self.root / "key").stat().st_mode & 0o777, 0o600)
        with PrivateFiles(self.root) as files:
            self.assertEqual(files.read("key"), b"synthetic-key")
        self.assertEqual([p.name for p in self.root.iterdir()], ["key"])

    def test_existing_key_is_never_overwritten_by_provisioning(self):
        self.write()
        with PrivateFiles(self.root) as files:
            with self.assertRaises(FileExistsError):
                files.publish("key", b"replacement", exclusive=True)
            self.assertEqual(files.read("key"), b"synthetic-key")
        self.assertEqual([p.name for p in self.root.iterdir()], ["key"])

    def test_permissive_directory_is_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(Locked):
            PrivateFiles(self.root)

    def test_permissive_key_is_rejected(self):
        self.write()
        (self.root / "key").chmod(0o644)
        with PrivateFiles(self.root) as files, self.assertRaises(Locked):
            files.read("key")

    def test_symbolic_key_is_rejected(self):
        self.write("actual")
        (self.root / "key").symlink_to(self.root / "actual")
        with PrivateFiles(self.root) as files, self.assertRaises(Locked):
            files.read("key")

    def test_symbolic_namespace_is_rejected(self):
        target = self.root / "target"
        target.mkdir(mode=0o700)
        link = self.root / "link"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(Locked):
            PrivateFiles(link)

    def test_hardlinked_key_is_rejected(self):
        self.write()
        os.link(self.root / "key", self.root / "another-link")
        with PrivateFiles(self.root) as files, self.assertRaises(Locked):
            files.read("key")

    def test_fifo_is_rejected_without_blocking(self):
        os.mkfifo(self.root / "key", 0o600)
        with PrivateFiles(self.root) as files, self.assertRaises(Locked):
            files.read("key")

    def test_oversized_file_is_rejected(self):
        self.write(content=b"x" * 33)
        with PrivateFiles(self.root) as files, self.assertRaises(Locked):
            files.read("key", 32)

    def test_names_cannot_escape_the_namespace(self):
        with PrivateFiles(self.root) as files:
            for name in ("../key", "/key", "", ".", "..", "a\0b", "a\nb", "a" * 129):
                with self.subTest(name=repr(name)), self.assertRaises(Locked):
                    files.read(name)

    def test_failed_replacement_preserves_the_previous_record(self):
        self.write()
        with PrivateFiles(self.root) as files:
            with patch("os.replace", side_effect=OSError("synthetic interruption")):
                with self.assertRaises(OSError):
                    files.publish("key", b"replacement")
            self.assertEqual(files.read("key"), b"synthetic-key")
        self.assertEqual([p.name for p in self.root.iterdir()], ["key"])

    def test_foreign_owner_is_rejected(self):
        with patch("os.geteuid", return_value=os.geteuid() + 1):
            with self.assertRaises(Locked):
                PrivateFiles(self.root)
