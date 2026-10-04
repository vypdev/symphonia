from __future__ import annotations

import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from symphonia.runtime import container_entrypoint


class ContainerEntrypointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name) / "data"
        self.data.mkdir()

    def test_prepares_only_data_directory_and_known_database_files(self) -> None:
        database = self.data / "symphonia.sqlite3"
        database.write_bytes(b"SQLite fixture")
        wal = self.data / "symphonia.sqlite3-wal"
        wal.write_bytes(b"WAL fixture")
        options = self.data / "options.json"
        options.write_text("{}", encoding="utf-8")

        with patch.object(container_entrypoint.os, "chown") as chown:
            container_entrypoint.prepare_data_directory(self.data, 1001, 1002)

        self.assertEqual(
            [call.args[0] for call in chown.call_args_list],
            [self.data, database, wal],
        )
        self.assertTrue(all(call.kwargs == {"follow_symlinks": False} for call in chown.call_args_list))
        self.assertNotIn(options, [call.args[0] for call in chown.call_args_list])

    def test_rejects_symlinked_or_linked_database_before_chowning_it(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.write_bytes(b"keep")
        database = self.data / "symphonia.sqlite3"
        database.symlink_to(outside)
        with patch.object(container_entrypoint.os, "chown") as chown:
            with self.assertRaisesRegex(ValueError, "private regular file"):
                container_entrypoint.prepare_data_directory(self.data, 1001, 1002)
        chown.assert_not_called()
        self.assertEqual(outside.read_bytes(), b"keep")

        database.unlink()
        os.link(outside, database)
        with patch.object(container_entrypoint.os, "chown") as chown:
            with self.assertRaisesRegex(ValueError, "private regular file"):
                container_entrypoint.prepare_data_directory(self.data, 1001, 1002)
        chown.assert_not_called()

    def test_rejects_a_data_directory_symlink(self) -> None:
        link = Path(self.temporary.name) / "data-link"
        link.symlink_to(self.data, target_is_directory=True)
        with patch.object(container_entrypoint.os, "chown") as chown:
            with self.assertRaisesRegex(ValueError, "real directory"):
                container_entrypoint.prepare_data_directory(link, 1001, 1002)
        chown.assert_not_called()

    def test_drops_groups_gid_and_uid_before_execing_service(self) -> None:
        actions: list[object] = []
        account = SimpleNamespace(pw_uid=1001, pw_gid=1002)
        with (
            patch.object(container_entrypoint.os, "geteuid", return_value=0),
            patch.object(container_entrypoint.pwd, "getpwnam", return_value=account),
            patch.object(container_entrypoint, "prepare_data_directory", side_effect=lambda *_: actions.append("prepare")),
            patch.object(container_entrypoint.os, "setgroups", side_effect=lambda groups: actions.append(("groups", groups))),
            patch.object(container_entrypoint.os, "setgid", side_effect=lambda gid: actions.append(("gid", gid))),
            patch.object(container_entrypoint.os, "setuid", side_effect=lambda uid: actions.append(("uid", uid))),
            patch.object(container_entrypoint.os, "execv", side_effect=lambda executable, argv: actions.append(("exec", argv))),
        ):
            container_entrypoint.main()

        self.assertEqual(actions[:4], ["prepare", ("groups", []), ("gid", 1002), ("uid", 1001)])
        self.assertEqual(actions[4][0], "exec")
        self.assertEqual(actions[4][1][-2:], ["-m", "symphonia"])

    def test_refuses_to_initialize_without_root(self) -> None:
        with patch.object(container_entrypoint.os, "geteuid", return_value=1001):
            with self.assertRaisesRegex(RuntimeError, "requires root"):
                container_entrypoint.main()


if __name__ == "__main__":
    unittest.main()
