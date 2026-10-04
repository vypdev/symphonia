"""Prepare Supervisor's mounted data directory, then run the service unprivileged."""

from __future__ import annotations

import os
from pathlib import Path
import pwd
import stat
import sys


SERVICE_USER = "symphonia"
DATABASE_FILES = (
    "symphonia.sqlite3",
    "symphonia.sqlite3-wal",
    "symphonia.sqlite3-shm",
    "symphonia.sqlite3-journal",
)


def prepare_data_directory(directory: Path, uid: int, gid: int) -> None:
    """Own only the App directory and known SQLite files after a restore.

    Supervisor creates the bind-mounted directory as root.  Avoid recursively
    changing unrelated files such as its options.json, and never follow links.
    """
    mode = directory.lstat().st_mode
    if not stat.S_ISDIR(mode):
        raise ValueError("App data path must be a real directory")
    existing_files: list[Path] = []
    for name in DATABASE_FILES:
        path = directory / name
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError(f"App database file is not a private regular file: {name}")
        existing_files.append(path)
    os.chown(directory, uid, gid, follow_symlinks=False)
    for path in existing_files:
        os.chown(path, uid, gid, follow_symlinks=False)


def main() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("App container initialization requires root")
    account = pwd.getpwnam(SERVICE_USER)
    prepare_data_directory(Path("/data"), account.pw_uid, account.pw_gid)
    os.setgroups([])
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    os.execv(sys.executable, [sys.executable, "-m", "symphonia"])


if __name__ == "__main__":
    main()
