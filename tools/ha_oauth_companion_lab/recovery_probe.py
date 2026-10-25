"""Synthetic multi-record recovery research; no production/authentication API.

Explicit reset's boolean is an internal TEST admission stub. It proves durable
ordering, never native HA/Ingress authorization. That gate remains separate.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys

from tools.ha_oauth_companion_lab.key_custody_probe import Locked, PrivateFiles, encoded, seal, unseal
from tools.ha_oauth_companion_lab.key_publication_probe import MARKER, Vault


CONNECTIONS = ("a", "b", "c")
OLD = {name: ("synthetic-old-"+name).encode() for name in CONNECTIONS}
NEW = {name: ("synthetic-new-"+name).encode() for name in CONNECTIONS}


class RecoveryVault(Vault):
    @classmethod
    def create(cls, root):
        root.mkdir(mode=0o700)
        for name in ("keys", "records"):
            (root/name).mkdir(mode=0o700)
        with PrivateFiles(root) as files:
            files.publish("owned.json", encoded({"marker":MARKER}), exclusive=True)
        key_ref = secrets.token_hex(16)
        with PrivateFiles(root/"keys") as files:
            files.publish(key_ref, secrets.token_bytes(32), exclusive=True)
        db = sqlite3.connect(root/"state.sqlite")
        os.chmod(root/"state.sqlite", 0o600)
        try:
            db.executescript("CREATE TABLE state(singleton INTEGER PRIMARY KEY,epoch INTEGER,key_ref TEXT,record_ref TEXT);"
                "CREATE TABLE history(value TEXT); INSERT INTO history VALUES('retained-synthetic-history');"
                "CREATE TABLE live(name TEXT PRIMARY KEY,reference TEXT);"
                "CREATE TABLE owners(id TEXT PRIMARY KEY,epoch INTEGER,key_ref TEXT,refs TEXT,live INTEGER);"
                "CREATE TABLE lifecycle(phase TEXT); INSERT INTO lifecycle VALUES('active');")
            db.execute("INSERT INTO state VALUES(1,0,?,NULL)", (key_ref,))
            db.commit()
        finally:
            db.close()
        vault = cls(root)
        try:
            refs = vault.records(key_ref, OLD)
            vault.db.execute("BEGIN IMMEDIATE")
            vault.db.executemany("INSERT INTO live VALUES(?,?)", refs.items())
            vault.db.execute("UPDATE state SET record_ref=?", (refs["a"],))
            vault.db.commit()
        finally:
            vault.close()

    def phase(self):
        return self.db.execute("SELECT phase FROM lifecycle").fetchone()[0]

    def snapshot(self):
        own = not self.db.in_transaction
        if own:
            self.db.execute("BEGIN")
        try:
            epoch, key = self.db.execute("SELECT epoch,key_ref FROM state").fetchone()
            refs = dict(self.db.execute("SELECT name,reference FROM live ORDER BY name"))
            return epoch, key, encoded(refs).decode()
        finally:
            if own:
                self.db.rollback()

    def aad_for(self, name, key, ref):
        return encoded({"version":1, "profile":"oauth", "installation":self.root.name,
                        "connection":name, "key_ref":key, "record_ref":ref})

    def records(self, key, values, *, checkpoint=lambda point: None):
        if set(values) != set(CONNECTIONS):
            raise Locked("incomplete_fixture_connections")
        refs = {}
        for name in CONNECTIONS:
            ref = secrets.token_hex(16)
            record = encoded(seal(self.key(key), values[name], self.aad_for(name, key, ref)))
            checkpoint("before_record")
            with PrivateFiles(self.root/"records") as files:
                files.publish(ref, record, exclusive=True)
            refs[name] = ref
            checkpoint("record_"+name)
        return refs

    def read_refs(self, key, refs):
        raw_key = self.key(key)
        values = {}
        with PrivateFiles(self.root/"records") as files:
            for name, ref in refs.items():
                record = json.loads(files.read(self.identifier(ref)))
                values[name] = unseal(raw_key, record, self.aad_for(name, key, ref))
        return values

    def read_all(self):
        own = not self.db.in_transaction
        if own:
            self.db.execute("BEGIN")
        try:
            phase = self.phase()
            if phase not in {"active", "unpaired"}:
                raise Locked("reset_pending_or_invalid_phase")
            _, key, raw = self.snapshot()
            refs = json.loads(raw)
            primary = self.db.execute("SELECT record_ref FROM state").fetchone()[0]
            if ((phase=="active" and (set(refs)!=set(CONNECTIONS) or primary!=refs["a"]))
                    or (phase=="unpaired" and (refs or primary is not None))):
                raise Locked("inconsistent_fixture_reference_set")
            return self.read_refs(key, refs)
        finally:
            if own:
                self.db.rollback()

    def admit(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.phase() != "active" or self.db.execute("SELECT COUNT(*) FROM owners WHERE live=1").fetchone()[0]:
                raise Locked("fixture_owner_unavailable")
            self.read_all()
            snapshot = self.snapshot()
            owner = secrets.token_hex(16)
            self.db.execute("INSERT INTO owners VALUES(?,?,?,?,1)", (owner, *snapshot))
            self.db.commit()
            return owner
        except BaseException:
            self.db.rollback()
            raise

    def stage_owner(self, owner, *, rotate=False, checkpoint=lambda point: None):
        row = self.db.execute("SELECT epoch,key_ref,refs,live FROM owners WHERE id=?", (owner,)).fetchone()
        if not row or not row[3] or self.phase() != "active" or tuple(row[:3]) != self.snapshot():
            raise Locked("owner_fenced")
        key = row[1]
        self.read_refs(key, json.loads(row[2]))
        if rotate:
            key = secrets.token_hex(16)
            with PrivateFiles(self.root/"keys") as files:
                files.publish(key, secrets.token_bytes(32), exclusive=True)
            checkpoint("key_staged")
        return key, self.records(key, NEW, checkpoint=checkpoint)

    def activate_owner(self, owner, candidate, *, checkpoint=lambda point: None):
        key, refs = candidate
        if set(refs) != set(CONNECTIONS):
            raise Locked("incomplete_fixture_connections")
        self.read_refs(key, refs)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT epoch,key_ref,refs,live FROM owners WHERE id=?", (owner,)).fetchone()
            admitted = bool(row and row[3] and self.phase() == "active" and tuple(row[:3]) == self.snapshot())
            if admitted:
                self.db.execute("UPDATE state SET key_ref=?,record_ref=?", (key, refs["a"]))
                self.db.executemany("UPDATE live SET reference=? WHERE name=?", ((ref,name) for name,ref in refs.items()))
            self.db.execute("UPDATE owners SET live=0 WHERE id=?", (owner,))
            checkpoint("before_commit")
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        checkpoint("after_commit")
        return admitted

    def collect_quiescent(self, *, checkpoint=lambda point: None):
        # The SQL lock excludes new admission; live owners conservatively pin ALL
        # staged files, even before their generated references enter SQL.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.phase() == "reset_pending" or self.db.execute("SELECT COUNT(*) FROM owners WHERE live=1").fetchone()[0]:
                self.db.commit()
                return False
            self.read_all()
            _, key, raw = self.snapshot()
            refs = set(json.loads(raw).values())
            for folder, keep, point in (("records",refs,"records_retired"),("keys",{key},"keys_retired")):
                with PrivateFiles(self.root/folder) as files:
                    for path in (self.root/folder).iterdir():
                        name = self.identifier(path.name)
                        if name not in keep:
                            files.read(name)
                            os.unlink(name, dir_fd=files.fd)
                    os.fsync(files.fd)
                checkpoint(point)
            self.db.commit()
            return True
        except BaseException:
            self.db.rollback()
            raise

    def recover_after_all_writers_exit(self):
        # Explicit caller condition: parent has joined every killed child.
        # This is NOT a live lease-expiration or distributed GC algorithm.
        if self.phase() == "reset_pending":
            return "reset_pending"
        self.read_all()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("UPDATE owners SET live=0")
            self.db.execute("UPDATE state SET epoch=epoch+1")
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        self.collect_quiescent()
        return self.phase()

    def explicit_reset(self, *, test_authorized=False, resume=False, checkpoint=lambda point: None):
        # This internal boolean is a test-only authorization stub. No HTTP
        # endpoint may turn caller input into this authority in production.
        if test_authorized is not True:
            raise Locked("reset_not_authorized")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if resume:
                if self.phase() != "reset_pending":
                    raise Locked("no_reset_intent")
            else:
                if self.phase() == "reset_pending":
                    raise Locked("explicit_resume_required")
                self.db.execute("UPDATE state SET epoch=epoch+1,record_ref=NULL")
                self.db.execute("DELETE FROM live")
                self.db.execute("UPDATE owners SET live=0")
                self.db.execute("UPDATE lifecycle SET phase='reset_pending'")
            epoch = self.snapshot()[0]
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        checkpoint("reset_fenced")
        key = secrets.token_hex(16)
        with PrivateFiles(self.root/"keys") as files:
            files.publish(key, secrets.token_bytes(32), exclusive=True)
        checkpoint("reset_key_staged")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.phase() != "reset_pending" or self.snapshot()[0] != epoch:
                raise Locked("reset_fenced_by_competitor")
            self.db.execute("UPDATE state SET key_ref=?", (key,))
            self.db.execute("UPDATE lifecycle SET phase='unpaired'")
            checkpoint("reset_before_commit")
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        checkpoint("reset_after_commit")


def child(root, mode, point):
    def checkpoint(current):
        if current == point:
            os._exit(83)
    vault = RecoveryVault(root)
    try:
        if mode == "reset":
            vault.explicit_reset(test_authorized=True, checkpoint=checkpoint)
        else:
            owner = vault.admit()
            candidate = vault.stage_owner(owner, rotate=mode=="rotate", checkpoint=checkpoint)
            assert vault.activate_owner(owner, candidate, checkpoint=checkpoint)
            vault.collect_quiescent(checkpoint=checkpoint)
    finally:
        vault.close()


def campaign(base):
    if base != Path("/data/recovery-lab") or os.geteuid() != 10001:
        raise Locked("wrong_disposable_context")
    base.mkdir(mode=0o700)
    results = {}
    plans = (("publish",("before_record","record_a","before_commit","after_commit")),
             ("rotate",("key_staged","record_a","record_c","before_commit","after_commit","records_retired")),
             ("reset",("reset_fenced","reset_key_staged","reset_before_commit","reset_after_commit")))
    for mode, points in plans:
        for point in points:
            root = base/(mode+"-"+point)
            RecoveryVault.create(root)
            completed = subprocess.run([sys.executable,__file__,"child",str(root),mode,point],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15,
                env={"PATH":os.environ.get("PATH", ""),"PYTHONPATH":"/research","PYTHONDONTWRITEBYTECODE":"1"})
            assert completed.returncode == 83
            vault = RecoveryVault(root)
            try:
                before_keys = sorted(p.name for p in (root/"keys").iterdir())
                phase = vault.recover_after_all_writers_exit()
                if mode == "reset":
                    assert {p.name for p in (root/"keys").iterdir()} <= set(before_keys)
                    assert phase == ("unpaired" if point=="reset_after_commit" else "reset_pending")
                    if phase == "reset_pending":
                        try:
                            vault.read_all()
                        except Locked:
                            pass
                        else:
                            raise AssertionError("reset_not_locked")
                        vault.explicit_reset(test_authorized=True,resume=True)
                    assert vault.phase() == "unpaired" and vault.read_all() == {}
                    vault.collect_quiescent()
                else:
                    assert vault.read_all() == (NEW if point in {"after_commit","records_retired"} else OLD)
                    assert len(list((root/"keys").iterdir())) == 1
                    assert len(list((root/"records").iterdir())) == 3
                assert vault.db.execute("SELECT value FROM history").fetchone()[0] == "retained-synthetic-history"
                results[mode+"-"+point] = True
            finally:
                vault.close()
    return {"mode":"synthetic_multi_record_recovery", "process_deaths":14,"results":results,
            "uid":os.geteuid(),"real_ha_or_provider":False,"native_reset_admission_or_live_lease_expiry_proven":False}


if __name__ == "__main__":
    try:
        if len(sys.argv)>1 and sys.argv[1]=="child":
            child(Path(sys.argv[2]),sys.argv[3],sys.argv[4])
        else:
            print(json.dumps(campaign(Path("/data/recovery-lab")),sort_keys=True))
    except Exception as error:
        print(json.dumps({"mode":"recovery_probe_failed","exception_type":type(error).__name__}))
        raise SystemExit(1) from None
