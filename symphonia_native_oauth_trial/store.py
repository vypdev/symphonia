"""Finite trial state, durable admissions and atomic sealed publication."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import sqlite3

from .policy import Binding, TrialError, bootstrap, identifier, integer, lifetime, private_file


class Store:
    def __init__(self, path: Path, *, checkpoint=lambda name: None):
        self.path, self.checkpoint = path, checkpoint
        try:
            info = path.lstat()
            private_file(mode=info.st_mode, owner=info.st_uid, expected_owner=os.getuid(),
                         links=info.st_nlink, size=info.st_size, maximum=4 * 1024 * 1024)
            self.db = sqlite3.connect(path, isolation_level=None, timeout=1)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA trusted_schema=OFF")
            if self.meta()["schema"] != 1:
                raise TrialError("locked")
            with self.transaction():
                self.db.execute("UPDATE attempt SET phase='uncertain' WHERE phase IN ('exchanging','refreshing')")
                self.db.execute("UPDATE attempt SET phase='cancelled' WHERE phase IN ('pending','staged')")
        except (OSError, ValueError, KeyError, sqlite3.Error):
            raise TrialError("locked") from None

    @classmethod
    def provision(cls, path: Path, installation: str, started: int) -> Store:
        """Only explicit first provision calls this; existing paths never rekey."""
        identifier(installation)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        db = sqlite3.connect(path)
        try:
            db.executescript("""
              CREATE TABLE metadata (id INTEGER PRIMARY KEY CHECK(id=1), document TEXT NOT NULL);
              CREATE TABLE attempt (id INTEGER PRIMARY KEY CHECK(id=1), binding TEXT NOT NULL,
                phase TEXT NOT NULL, owner TEXT, sealed BLOB, account TEXT, confirmation_flow TEXT);
            """)
            meta = {"schema": 1, "installation": installation, "started": started,
                    "deadline": started + 1200, "last_seen": started, "pair_epoch": 0,
                    "credential_epoch": 0, "pair_id": None, "actor": None, "peer": None,
                    "bootstrap_used": False, "retired": False}
            lifetime(started, meta["deadline"], started, started)
            db.execute("INSERT INTO metadata VALUES (1,?)", (json.dumps(meta),))
            db.commit()
        finally:
            db.close()
        return cls(path)

    @contextmanager
    def transaction(self):
        try:
            self.db.execute("BEGIN IMMEDIATE")
            yield
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def close(self):
        self.db.close()

    def meta(self):
        try:
            raw = self.db.execute("SELECT document FROM metadata WHERE id=1").fetchone()[0]
            if not isinstance(raw, str) or len(raw) > 8192:
                raise TrialError("locked")
            value = json.loads(raw)
            if not isinstance(value, dict) or set(value) != {"schema", "installation", "started", "deadline", "last_seen", "pair_epoch", "credential_epoch", "pair_id", "actor", "peer", "bootstrap_used", "retired"}:
                raise TrialError("locked")
            for name in ("schema", "started", "deadline", "last_seen", "pair_epoch", "credential_epoch"):
                integer(value[name])
            identifier(value["installation"])
            if type(value["bootstrap_used"]) is not bool or type(value["retired"]) is not bool:
                raise TrialError("locked")
            if value["pair_id"] is not None:
                identifier(value["pair_id"])
                identifier(value["actor"])
            if value["peer"] is not None and (not isinstance(value["peer"], str) or len(value["peer"]) != 64):
                raise TrialError("locked")
            return value
        except (sqlite3.Error, ValueError, KeyError, TypeError):
            raise TrialError("locked") from None

    def _save_meta(self, value):
        self.db.execute("UPDATE metadata SET document=? WHERE id=1", (json.dumps(value),))

    def _guard(self, now):
        meta = self.meta()
        lifetime(meta["started"], meta["deadline"], meta["last_seen"], now)
        if meta["retired"]:
            raise TrialError("expired")
        meta["last_seen"] = max(meta["last_seen"], int(now))
        self._save_meta(meta)
        return meta

    def _binding(self, binding, now):
        meta = self._guard(now)
        if (binding.installation != meta["installation"] or binding.pair_id != meta["pair_id"]
                or binding.actor != meta["actor"] or binding.pair_epoch != meta["pair_epoch"]
                or binding.credential_epoch != meta["credential_epoch"] or binding.deadline != meta["deadline"]):
            raise TrialError("invalid_binding")
        Binding.parse(binding.wire()).require(binding, now)
        return meta

    def enroll(self, actor: str, peer: str, now: float):
        identifier(actor)
        if not isinstance(peer, str) or len(peer) != 64 or any(c not in "0123456789abcdef" for c in peer):
            raise TrialError("tls_identity")
        with self.transaction():
            meta = self._guard(now)
            bootstrap(meta["started"], meta["started"] + 300, meta["bootstrap_used"], now)
            if meta["pair_id"] is not None:
                raise TrialError("bootstrap_unavailable")
            meta.update(pair_id=secrets.token_hex(16), actor=actor, peer=peer, bootstrap_used=True)
            self._save_meta(meta)
        return meta

    def start(self, binding: Binding, now: float):
        with self.transaction():
            self._binding(binding, now)
            if self.db.execute("SELECT 1 FROM attempt").fetchone():
                raise TrialError("conflict")
            self.db.execute("INSERT INTO attempt(id,binding,phase) VALUES (1,?,'pending')",
                            (json.dumps(binding.wire(), sort_keys=True),))

    def _attempt(self, binding, now):
        self._binding(binding, now)
        row = self.db.execute("SELECT * FROM attempt WHERE id=1").fetchone()
        if row is None:
            raise TrialError("conflict")
        Binding.parse(json.loads(row["binding"])).require(binding, now)
        return row

    def stage(self, binding: Binding, now: float):
        with self.transaction():
            row = self._attempt(binding, now)
            if row["phase"] != "pending":
                raise TrialError("conflict")
            self.db.execute("UPDATE attempt SET phase='staged' WHERE id=1")

    def validate_staged(self, binding: Binding, now: float):
        with self.transaction():
            if self._attempt(binding, now)["phase"] != "staged":
                raise TrialError("conflict")

    def claim(self, binding: Binding, now: float, *, refresh_flow: str | None = None):
        with self.transaction():
            row = self._attempt(binding, now)
            source, target = ("active", "refreshing") if refresh_flow is not None else ("staged", "exchanging")
            if row["phase"] in ("active", "verified", "exchanging", "refreshing") and row["phase"] != source:
                return None
            if row["phase"] != source:
                raise TrialError("uncertain" if row["phase"] == "uncertain" else "conflict")
            if refresh_flow is not None:
                identifier(refresh_flow)
                if refresh_flow == binding.flow:
                    raise TrialError("invalid_binding")
            owner = secrets.token_hex(16)
            self.db.execute("UPDATE attempt SET phase=?,owner=?,confirmation_flow=? WHERE id=1",
                            (target, owner, refresh_flow))
        return owner

    def commit(self, binding: Binding, owner: str, sealed: bytes, account: str, now: float, *, refreshed=False):
        if not isinstance(sealed, bytes) or not 1 <= len(sealed) <= 65536 or not isinstance(account, str) or len(account) != 64:
            raise TrialError("locked")
        with self.transaction():
            row = self._attempt(binding, now)
            if row["owner"] != owner or row["phase"] != ("refreshing" if refreshed else "exchanging"):
                raise TrialError("conflict")
            self.db.execute("UPDATE attempt SET sealed=?,account=? WHERE id=1", (sealed, account))
            self.checkpoint("ciphertext_staged")
            self.db.execute("UPDATE attempt SET phase=?,owner=NULL WHERE id=1", ("verified" if refreshed else "active",))

    def assert_owner(self, binding: Binding, owner: str, now: float):
        with self.transaction():
            row = self._attempt(binding, now)
            if row["owner"] != owner or row["phase"] not in ("exchanging", "refreshing"):
                raise TrialError("conflict")

    def finish_error(self, owner: str, *, uncertain: bool):
        with self.transaction():
            self.db.execute("UPDATE attempt SET phase=? WHERE id=1 AND owner=? AND phase IN ('exchanging','refreshing')",
                            ("uncertain" if uncertain else "failed", owner))

    def terminal(self, binding: Binding, now: float, phase: str):
        if phase not in ("denied", "cancelled"):
            raise TrialError("invalid_request")
        with self.transaction():
            row = self._attempt(binding, now)
            if row["phase"] not in ("pending", "staged"):
                raise TrialError("conflict")
            self.db.execute("UPDATE attempt SET phase=? WHERE id=1", (phase,))

    def grant(self, binding: Binding, now: float):
        with self.transaction():
            row = self._attempt(binding, now)
            if row["phase"] not in ("active", "verified", "refreshing") or row["sealed"] is None:
                raise TrialError("locked")
            return bytes(row["sealed"]), row["account"]

    def retire(self):
        with self.transaction():
            meta = self.meta()
            meta.update(retired=True, peer=None, pair_epoch=meta["pair_epoch"] + 1,
                        credential_epoch=meta["credential_epoch"] + 1)
            self._save_meta(meta)
            self.db.execute("UPDATE attempt SET phase='retired',sealed=NULL,owner=NULL WHERE id=1")

    def status(self, now: float):
        meta = self.meta()
        try:
            with self.transaction():
                self._guard(now)
        except TrialError as error:
            phase = "locked"
            if error.reason == "expired":
                phase = "retired" if meta["retired"] else "expired"
            return {"phase": phase, "deadline": meta["deadline"]}
        row = self.db.execute("SELECT phase FROM attempt WHERE id=1").fetchone()
        return {"phase": row[0] if row else "paired" if meta["pair_id"] else "unpaired", "deadline": meta["deadline"]}
