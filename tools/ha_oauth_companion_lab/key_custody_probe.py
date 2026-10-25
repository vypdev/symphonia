"""Opt-in local-key research, never imported by production packaging.

Use only an explicitly owned disposable /data volume. The fixture models an
App install-local AES-GCM key, process/container restart, excluded-key restore
and an externally held recovery key. It is not a production vault or a claim
that Core can exclude an integration's key files from its backup.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import tempfile


MARKER = "symphonia-local-key-research-v1"
MAX_RECORD = 131072
PROFILE = "oauth"


class Locked(Exception):
    """Safe, bounded failure; never embeds paths or secret bytes."""


class PrivateFiles:
    """Descriptor-relative operations inside an owned 0700 directory."""

    def __init__(self, path: Path):
        try:
            self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            raise Locked("unsafe_directory") from None
        try:
            info = os.fstat(self.fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise Locked("unsafe_directory")
        except BaseException:
            os.close(self.fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        os.close(self.fd)

    @staticmethod
    def _name(name):
        if (not isinstance(name, str) or not name or len(name) > 128 or "/" in name
                or name in {".", ".."} or any(ord(c) < 33 or ord(c) > 126 for c in name)):
            raise Locked("invalid_name")

    def read(self, name, limit=MAX_RECORD):
        self._name(name)
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        except OSError:
            raise Locked("private_file_unavailable") from None
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size > limit):
                raise Locked("unsafe_private_file")
            value = source.read(limit + 1)
            if len(value) > limit:
                raise Locked("private_file_too_large")
            return value

    def publish(self, name, value, *, exclusive=False, checkpoint=lambda point: None):
        self._name(name)
        if not isinstance(value, bytes) or len(value) > MAX_RECORD:
            raise Locked("invalid_private_value")
        temporary = ".pending-" + secrets.token_hex(16)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=self.fd)
        try:
            with os.fdopen(descriptor, "wb") as destination:
                os.fchmod(destination.fileno(), 0o600)
                checkpoint("private_opened")
                destination.write(value)
                checkpoint("private_written")
                destination.flush()
                os.fsync(destination.fileno())
                checkpoint("private_durable")
            if exclusive:
                # link is an atomic no-replace publication; remove the temporary
                # link before opening the file through the nlink=1 reader.
                os.link(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd,
                        follow_symlinks=False)
            else:
                os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            checkpoint("private_named")
            os.fsync(self.fd)
            checkpoint("private_named_durable")
        finally:
            try:
                os.unlink(temporary, dir_fd=self.fd)
            except FileNotFoundError:
                pass
            os.fsync(self.fd)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def seal(key, value, aad):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    return {"nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(AESGCM(key).encrypt(nonce, value, aad)).decode()}


def unseal(key, record, aad):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        if set(record) != {"nonce", "ciphertext"}:
            raise ValueError
        nonce = base64.b64decode(record["nonce"], validate=True)
        ciphertext = base64.b64decode(record["ciphertext"], validate=True)
        if len(nonce) != 12 or len(ciphertext) > MAX_RECORD:
            raise ValueError
        return AESGCM(key).decrypt(nonce, ciphertext, aad)
    except Exception:
        raise Locked("sealed_record_unavailable") from None


def initialize(root, plaintext):
    """Fresh provisioning only: existing metadata/data must never mint a key."""
    if list(root.iterdir()):
        raise Locked("not_a_fresh_install")
    with PrivateFiles(root) as files:
        files.publish("owned.json", encoded({"marker": MARKER}), exclusive=True)
        installation = secrets.token_hex(16)
        # Persist the initialization intent first. Interrupted setup is locked;
        # startup is never allowed to reinterpret it as a blank installation.
        files.publish("identity.json", encoded({"installation": installation, "version": 1}), exclusive=True)
    keys = root / "keys"
    keys.mkdir(mode=0o700)
    key = secrets.token_bytes(32)
    with PrivateFiles(keys) as files:
        files.publish("install.key", key, exclusive=True)
    metadata = {"installation": installation, "version": 1, "profile": PROFILE}
    record = {"metadata": metadata, "sealed": seal(key, plaintext, encoded(metadata))}
    with PrivateFiles(root) as files:
        files.publish("grant.json", encoded(record), exclusive=True)
        # A high-entropy synthetic canary digest permits a second container to
        # check recovery without storing or printing the plaintext fixture.
        files.publish("expected.json", encoded({"digest": hashlib.sha256(plaintext).hexdigest(),
                      "key_digest": hashlib.sha256(key).hexdigest()}), exclusive=True)


def boot(root, *, profile=PROFILE):
    """Read-only boot: no missing key/record can trigger replacement."""
    try:
        with PrivateFiles(root) as files:
            if json.loads(files.read("owned.json")) != {"marker": MARKER}:
                raise Locked("unowned_fixture")
            identity = json.loads(files.read("identity.json"))
            record = json.loads(files.read("grant.json"))
        if (set(identity) != {"installation", "version"} or type(identity["version"]) is not int
                or identity["version"] != 1 or set(record) != {"metadata", "sealed"}
                or record["metadata"] != {**identity, "profile": profile}):
            raise Locked("identity_or_profile_mismatch")
        with PrivateFiles(root / "keys") as files:
            key = files.read("install.key", 32)
        if len(key) != 32:
            raise Locked("invalid_key_length")
        return unseal(key, record["sealed"], encoded(record["metadata"]))
    except Locked:
        raise
    except Exception:
        raise Locked("local_key_unavailable") from None


def restart_check(root):
    value = boot(root)
    with PrivateFiles(root) as files:
        expected = json.loads(files.read("expected.json"))
    with PrivateFiles(root / "keys") as files:
        key = files.read("install.key", 32)
    assert hashlib.sha256(value).hexdigest() == expected["digest"]
    assert hashlib.sha256(key).hexdigest() == expected["key_digest"]
    return {"separate_container_boot": True, "same_key_and_grant": True,
            "boot_created_no_key": True, "uid": os.geteuid()}


def campaign(root):
    import cryptography
    receipt = {"mode": "install_local_key_research", "cryptography": cryptography.__version__,
               "uid": os.geteuid(), "personal_or_provider_credentials": False}
    plaintext = b"SYNTHETIC-GRANT-" + secrets.token_bytes(48)
    initialize(root, plaintext)
    receipt["fresh_provision_and_boot"] = boot(root) == plaintext
    try:
        initialize(root, plaintext)
    except Locked:
        receipt["existing_install_never_reinitialized"] = True
    else:
        receipt["existing_install_never_reinitialized"] = False
    receipt["grant_absent_from_sealed_record"] = plaintext not in (root / "grant.json").read_bytes()
    with PrivateFiles(root / "keys") as files:
        key = files.read("install.key", 32)
    receipt["wrapping_key_outside_record"] = key not in (root / "grant.json").read_bytes()
    receipt["key_permissions_0600"] = stat.S_IMODE((root / "keys/install.key").stat().st_mode) == 0o600

    def rejects(path, **kwargs):
        try:
            boot(path, **kwargs)
        except Locked:
            return True
        return False

    with tempfile.TemporaryDirectory(prefix="symphonia-key-fixtures-") as scratch:
        scratch = Path(scratch)

        def clone(name, include_key=True):
            target = scratch / name
            shutil.copytree(root, target, ignore=None if include_key else shutil.ignore_patterns("keys"))
            target.chmod(0o700)
            return target

        restored = clone("ordinary-backup", include_key=False)
        before = sorted(str(p.relative_to(restored)) for p in restored.rglob("*"))
        receipt["restore_without_key_locked"] = rejects(restored)
        receipt["restore_never_mints_a_key"] = before == sorted(str(p.relative_to(restored)) for p in restored.rglob("*"))
        wrong = clone("wrong-key")
        (wrong / "keys/install.key").write_bytes(secrets.token_bytes(32))
        receipt["wrong_install_key_rejected"] = rejects(wrong)
        permissive = clone("public-key-file")
        (permissive / "keys/install.key").chmod(0o644)
        receipt["permissive_key_rejected"] = rejects(permissive)
        permissive_dir = clone("public-key-directory")
        (permissive_dir / "keys").chmod(0o755)
        receipt["permissive_key_directory_rejected"] = rejects(permissive_dir)
        linked = clone("symlink-key")
        (linked / "keys/install.key").unlink()
        (linked / "keys/install.key").symlink_to(root / "keys/install.key")
        receipt["symlink_key_rejected"] = rejects(linked)
        linked_dir = clone("symlink-directory")
        shutil.rmtree(linked_dir / "keys")
        (linked_dir / "keys").symlink_to(root / "keys", target_is_directory=True)
        receipt["symlink_directory_rejected"] = rejects(linked_dir)
        hardlinked = clone("hardlink-key")
        os.link(hardlinked / "keys/install.key", hardlinked / "extra-key-link")
        receipt["hardlink_key_rejected"] = rejects(hardlinked)
        malformed = clone("short-key")
        (malformed / "keys/install.key").write_bytes(b"short")
        receipt["short_key_rejected"] = rejects(malformed)
        malformed = clone("large-key")
        (malformed / "keys/install.key").write_bytes(secrets.token_bytes(33))
        receipt["oversized_key_rejected"] = rejects(malformed)
        tampered = clone("tampered-record")
        value = json.loads((tampered / "grant.json").read_bytes())
        raw = base64.b64decode(value["sealed"]["ciphertext"])
        value["sealed"]["ciphertext"] = base64.b64encode(raw[:-1] + bytes([raw[-1] ^ 1])).decode()
        (tampered / "grant.json").write_bytes(encoded(value))
        receipt["tampered_record_rejected"] = rejects(tampered)
        receipt["playback_profile_cannot_read_oauth"] = rejects(root, profile="playback")
        other = clone("wrong-installation")
        value = json.loads((other / "identity.json").read_bytes())
        value["installation"] = secrets.token_hex(16)
        (other / "identity.json").write_bytes(encoded(value))
        receipt["wrong_installation_rejected"] = rejects(other)

        # Recovery is a distinct, opt-in owner action. Its random recovery key
        # is outside both the ordinary backup and the encrypted recovery kit.
        recovery_key = secrets.token_bytes(32)
        recovery_aad = b"symphonia/local-key-research/app-recovery/v1"
        kit = seal(recovery_key, key, recovery_aad)
        receipt["recovery_kit_contains_no_plaintext_key"] = key not in encoded(kit)
        try:
            unseal(secrets.token_bytes(32), kit, recovery_aad)
        except Locked:
            receipt["wrong_recovery_key_rejected"] = True
        else:
            receipt["wrong_recovery_key_rejected"] = False
        recovered = unseal(recovery_key, kit, recovery_aad)
        (restored / "keys").mkdir(mode=0o700)
        with PrivateFiles(restored / "keys") as files:
            files.publish("install.key", recovered, exclusive=True)
        receipt["explicit_external_key_recovery"] = boot(restored) == plaintext
        receipt["recovery_key_absent_from_ordinary_files"] = all(
            recovery_key not in p.read_bytes() for p in root.rglob("*") if p.is_file())

    assert all(value for name, value in receipt.items() if isinstance(value, bool)
               and name != "personal_or_provider_credentials")
    receipt["assertions"] = sum(isinstance(value, bool) and value for value in receipt.values())
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("campaign", "restart-check"))
    parser.add_argument("--root", type=Path, default=Path("/data/vault"))
    args = parser.parse_args()
    try:
        if args.mode == "campaign":
            # The lab command prepares only its newly labelled volume. This
            # is not an App entrypoint and accepts no real installation path.
            if args.root != Path("/data/vault") or os.geteuid() != 10001:
                raise Locked("wrong_lab_context")
            args.root.mkdir(mode=0o700)
            result = campaign(args.root)
        else:
            result = restart_check(args.root)
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        print(json.dumps({"mode": "key_research_failed", "exception_type": type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
