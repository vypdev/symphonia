"""Synthetic file/SQLite crash experiment, not the production secret adapter.

Run only as UID 10001 on a fresh owned /data/publication-lab volume, with the
pinned research image's cryptography package. No network/provider/HA access.
The collector is deliberately quiescent; live writer/lease/reset UX is unproven.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys

from tools.ha_oauth_companion_lab.key_custody_probe import Locked, PrivateFiles, encoded, seal, unseal


MARKER = "symphonia-publication-crash-research-v1"
OLD, NEW = b"synthetic-old-grant", b"synthetic-new-grant"
CRASH_EXIT = 83


class Vault:
    def __init__(self, root):
        self.root = root
        with PrivateFiles(root) as files:
            if json.loads(files.read("owned.json")) != {"marker": MARKER}:
                raise Locked("unowned_publication_fixture")
        self.db = sqlite3.connect(root / "state.sqlite", isolation_level=None)
        self.db.execute("PRAGMA synchronous=FULL")

    def close(self):
        self.db.close()

    @classmethod
    def create(cls, root):
        root.mkdir(mode=0o700)
        (root / "keys").mkdir(mode=0o700)
        (root / "records").mkdir(mode=0o700)
        with PrivateFiles(root) as files:
            files.publish("owned.json", encoded({"marker": MARKER}), exclusive=True)
        key_ref = secrets.token_hex(16)
        with PrivateFiles(root / "keys") as files:
            files.publish(key_ref, secrets.token_bytes(32), exclusive=True)
        db = sqlite3.connect(root / "state.sqlite")
        os.chmod(root / "state.sqlite", 0o600)
        try:
            db.execute("CREATE TABLE state (singleton INTEGER PRIMARY KEY, epoch INTEGER, key_ref TEXT, record_ref TEXT)")
            db.execute("CREATE TABLE history (value TEXT)")
            db.execute("INSERT INTO state VALUES (1,0,?,NULL)", (key_ref,))
            db.execute("INSERT INTO history VALUES ('retained-synthetic-history')")
            db.commit()
        finally:
            db.close()
        vault = cls(root)
        try:
            snapshot = vault.snapshot()
            candidate = vault.stage(OLD, snapshot)
            assert vault.activate(snapshot, candidate)
        finally:
            vault.close()

    def snapshot(self):
        return tuple(self.db.execute("SELECT epoch,key_ref,record_ref FROM state WHERE singleton=1").fetchone())

    def aad(self, key_ref, record_ref):
        return encoded({"version": 1, "profile": "oauth", "installation": self.root.name,
                        "key_ref": key_ref, "record_ref": record_ref})

    @staticmethod
    def identifier(value):
        if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{32}", value) is None:
            raise Locked("unsafe_fixture_reference")
        return value

    def key(self, reference):
        with PrivateFiles(self.root / "keys") as files:
            value = files.read(self.identifier(reference), 32)
        if len(value) != 32:
            raise Locked("invalid_fixture_key")
        return value

    def stage(self, plaintext, snapshot, *, rotate=False, checkpoint=lambda point: None):
        key_ref = snapshot[1]
        self.key(key_ref)  # Rotation cannot turn missing state into provisioning.
        if rotate:
            key_ref = secrets.token_hex(16)
            with PrivateFiles(self.root / "keys") as files:
                files.publish(key_ref, secrets.token_bytes(32), exclusive=True)
            checkpoint("key_staged")
        record_ref = secrets.token_hex(16)
        record = encoded(seal(self.key(key_ref), plaintext, self.aad(key_ref, record_ref)))
        checkpoint("before_record")
        with PrivateFiles(self.root / "records") as files:
            files.publish(record_ref, record, exclusive=True)
        checkpoint("record_staged")
        return key_ref, record_ref

    def activate(self, snapshot, candidate, *, checkpoint=lambda point: None):
        key_ref, record_ref = candidate
        self.key(key_ref)
        with PrivateFiles(self.root / "records") as files:
            unseal(self.key(key_ref), json.loads(files.read(self.identifier(record_ref))), self.aad(key_ref, record_ref))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            cursor = self.db.execute("UPDATE state SET key_ref=?,record_ref=? WHERE singleton=1 AND epoch=? AND key_ref=? AND record_ref IS ?",
                                     (key_ref, record_ref, *snapshot))
            checkpoint("before_commit")
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        checkpoint("after_commit")
        return cursor.rowcount == 1

    def read(self):
        _, key_ref, record_ref = self.snapshot()
        key = self.key(key_ref)
        if record_ref is None:
            return None
        with PrivateFiles(self.root / "records") as files:
            record = json.loads(files.read(self.identifier(record_ref)))
        return unseal(key, record, self.aad(key_ref, record_ref))

    def collect_quiescent(self, *, checkpoint=lambda point: None):
        # Caller proves no live stage/activation owner. This is not runtime GC.
        self.read()
        _, key_ref, record_ref = self.snapshot()
        for folder, keep, point in (("records", record_ref, "records_retired"),
                                    ("keys", key_ref, "keys_retired")):
            with PrivateFiles(self.root / folder) as files:
                for path in (self.root / folder).iterdir():
                    name = self.identifier(path.name)
                    if name != keep:
                        files.read(name)  # Reject links/types/permissions before unlink.
                        os.unlink(name, dir_fd=files.fd)
                os.fsync(files.fd)
            checkpoint(point)

    def fence(self, *, disconnect=False):
        self.db.execute("UPDATE state SET epoch=epoch+1" + (",record_ref=NULL" if disconnect else "") + " WHERE singleton=1")


def child(root, point, rotate):
    def checkpoint(current):
        if current == point:
            os._exit(CRASH_EXIT)  # Deliberately bypass Python/SQLite cleanup.
    vault = Vault(root)
    try:
        snapshot = vault.snapshot()
        candidate = vault.stage(NEW, snapshot, rotate=rotate, checkpoint=checkpoint)
        assert vault.activate(snapshot, candidate, checkpoint=checkpoint)
        vault.collect_quiescent(checkpoint=checkpoint)
    finally:
        vault.close()


def campaign(base):
    if base != Path("/data/publication-lab") or os.geteuid() != 10001:
        raise Locked("wrong_disposable_context")
    base.mkdir(mode=0o700)  # Refuse existing state; no recursive replacement.
    results = {}
    for rotation, points in ((False, ("before_record", "record_staged", "before_commit", "after_commit")),
                             (True, ("key_staged", "record_staged", "after_commit", "records_retired"))):
        for point in points:
            root = base / (("rotation-" if rotation else "publish-") + point)
            Vault.create(root)
            completed = subprocess.run([sys.executable, __file__, "child", "--root", str(root),
                "--point", point, *(["--rotate"] if rotation else [])],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=15, env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": "/research", "PYTHONDONTWRITEBYTECODE": "1"})
            assert completed.returncode == CRASH_EXIT
            vault = Vault(root)
            try:
                expected = NEW if point in {"after_commit", "records_retired"} else OLD
                assert vault.read() == expected
                vault.collect_quiescent()
                assert len(list((root / "keys").iterdir())) == 1
                assert len(list((root / "records").iterdir())) == 1
                assert vault.db.execute("SELECT value FROM history").fetchone()[0] == "retained-synthetic-history"
                assert OLD not in (root / "state.sqlite").read_bytes()
                assert NEW not in (root / "state.sqlite").read_bytes()
                results[root.name] = True
            finally:
                vault.close()
    for fence in ("disconnect", "re-pair", "competing"):
        root = base / fence
        Vault.create(root)
        vault = Vault(root)
        try:
            snapshot = vault.snapshot()
            candidate = vault.stage(NEW, snapshot)
            if fence == "competing":
                assert vault.activate(snapshot, vault.stage(OLD, snapshot))
            else:
                vault.fence(disconnect=fence == "disconnect")
            assert not vault.activate(snapshot, candidate)
            assert vault.read() == (None if fence == "disconnect" else OLD)
            vault.collect_quiescent()
            results[fence + "-fences-stale-publication"] = True
        finally:
            vault.close()
    root = base / "missing-key"
    Vault.create(root)
    vault = Vault(root)
    try:
        reference = vault.snapshot()[1]
        with PrivateFiles(root / "keys") as files:
            os.unlink(reference, dir_fd=files.fd)
        try:
            vault.read()
        except Locked:
            results["missing-key-locked-without-reprovision"] = not list((root / "keys").iterdir())
        else:
            raise AssertionError("missing_key_accepted")
    finally:
        vault.close()
    return {"mode": "synthetic_file_sql_crash_campaign", "uid": os.geteuid(),
            "process_death_cases": 8, "results": results, "personal_or_provider_credentials": False,
            "runtime_collector_or_reset_admission_proven": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("campaign", "child"))
    parser.add_argument("--root", type=Path, default=Path("/data/publication-lab"))
    parser.add_argument("--point")
    parser.add_argument("--rotate", action="store_true")
    args = parser.parse_args()
    if args.mode == "child":
        child(args.root, args.point, args.rotate)
    else:
        print(json.dumps(campaign(args.root), sort_keys=True))
