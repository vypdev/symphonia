"""Disposable Core private-key/backup proof for the owner-selected HA profile.

Execute only from the guarded symphonia-ha-lab. Creates an exact owned private
key and safe Store reference, never a real config entry. Reads only these two
members of generated Core backups. Core is never restored.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


ROOT = Path("/config/.symphonia-key-custody-lab-v1")
REFERENCE = Path("/config/.storage/symphonia_key_custody_safe_reference")
MARKER = "symphonia-synthetic-core-pair-key-v1"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


CHILD = r'''
import hashlib,json,os,stat,sys
from pathlib import Path
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
expected=json.loads(sys.stdin.read())
p=Path("/config/.symphonia-key-custody-lab-v1/pair.key")
fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
with os.fdopen(fd,"rb") as source:
    info=os.fstat(source.fileno())
    assert stat.S_ISREG(info.st_mode) and info.st_nlink==1
    assert info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o600
    raw=source.read(8193)
assert len(raw)<=8192
key=serialization.load_pem_private_key(raw,password=None)
public=key.public_key()
fingerprint=hashlib.sha256(public.public_bytes(serialization.Encoding.DER,
    serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()
assert fingerprint==expected["public_fingerprint"]
message=os.urandom(32)
signature=key.sign(message,ec.ECDSA(hashes.SHA256()))
public.verify(signature,message,ec.ECDSA(hashes.SHA256()))
print(json.dumps({"same_pair_key":True,"signature_verified":True}))
'''


async def campaign():
    import cryptography
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from homeassistant.const import __version__ as core_version
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.storage import Store
    from securetar import SecureTarError, SecureTarFile

    if os.environ.get("SYMPHONIA_DISPOSABLE_HA_LAB") != "symphonia-ha-lab":
        raise RuntimeError("explicit_disposable_lab_required")
    if ROOT.exists() or ROOT.is_symlink() or REFERENCE.exists() or REFERENCE.is_symlink():
        raise RuntimeError("unexpected_existing_fixture")
    token = os.environ["SUPERVISOR_TOKEN"]
    opener = build_opener(ProxyHandler({}), NoRedirect)
    created = []
    reference_bytes = None
    hass = HomeAssistant("/config")
    receipt = {"mode": "actual_core_private_key_protected_backup", "core": core_version,
               "cryptography": cryptography.__version__, "uid": os.geteuid(),
               "personal_or_provider_credentials": False, "core_restore_performed": False,
               "core_key_excluded_from_backup": False}

    def request(path, data=None, *, download=False, method=None):
        assert path.startswith("/backups/")
        body = json.dumps(data).encode() if data is not None else None
        req = Request("http://supervisor" + path, data=body, method=method,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with opener.open(req, timeout=300) as response:
                raw = response.read(128 * 1024 * 1024 + 1 if download else 1024 * 1024)
        except HTTPError as error:
            error.close()
            raise RuntimeError("lab_supervisor_request_failed") from None
        if download:
            assert len(raw) <= 128 * 1024 * 1024
            return raw
        result = json.loads(raw)
        assert result.get("result") == "ok"
        return result.get("data", {})

    def backup(password=None):
        payload = {"name": "Symphonia synthetic Core pairing key " + secrets.token_hex(16),
                   "homeassistant": True, "addons": [], "homeassistant_exclude_database": True,
                   "compressed": True}
        if password is not None:
            payload["password"] = password
        slug = request("/backups/new/partial", payload)["slug"]
        assert re.fullmatch(r"[a-f0-9]{1,64}", slug)
        created.append(slug)
        return request("/backups/" + slug + "/download", download=True)

    def selected_members(archive, password=None):
        selected = {}
        allowed = {"data/.symphonia-key-custody-lab-v1/pair.key",
                   "data/.storage/symphonia_key_custody_safe_reference"}
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as outer:
            member = outer.getmember("homeassistant.tar.gz")
            payload = outer.extractfile(member).read()
        with SecureTarFile(fileobj=io.BytesIO(payload), password=password) as inner:
            for member in inner:
                name = member.name.removeprefix("./")
                if name in allowed:
                    assert member.isfile() and member.size <= 16384
                    selected[name] = inner.extractfile(member).read()
        assert set(selected) == allowed
        return selected

    ROOT.mkdir(mode=0o700)
    (ROOT / ".owned").write_text(MARKER)
    (ROOT / ".owned").chmod(0o600)
    try:
        key = ec.generate_private_key(ec.SECP256R1())
        key_bytes = key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        descriptor = os.open(ROOT / "pair.key", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(key_bytes)
            destination.flush()
            os.fsync(destination.fileno())
        fingerprint = hashlib.sha256(key.public_key().public_bytes(serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()
        store = Store(hass, 1, "symphonia_key_custody_safe_reference", private=True)
        await store.async_save({"key_ref": "fixture-local-pair-key-v1", "public_fingerprint": fingerprint})
        reference_bytes = REFERENCE.read_bytes()
        receipt["private_key_file_0600"] = stat.S_IMODE((ROOT / "pair.key").stat().st_mode) == 0o600
        receipt["private_key_directory_0700"] = stat.S_IMODE(ROOT.stat().st_mode) == 0o700
        receipt["safe_store_file_0600"] = stat.S_IMODE(REFERENCE.stat().st_mode) == 0o600
        receipt["safe_store_contains_no_private_key"] = key_bytes not in reference_bytes
        child = subprocess.run([sys.executable, "-c", CHILD], input=json.dumps({"public_fingerprint": fingerprint}),
            text=True, capture_output=True, timeout=20,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"})
        assert child.returncode == 0
        receipt["new_process_same_key_and_signature"] = json.loads(child.stdout) == {
            "same_pair_key": True, "signature_verified": True}

        plain = selected_members(await asyncio.to_thread(backup))
        receipt["unprotected_core_archive_contains_pair_key"] = plain[
            "data/.symphonia-key-custody-lab-v1/pair.key"] == key_bytes
        receipt["backup_reference_contains_no_private_key"] = key_bytes not in plain[
            "data/.storage/symphonia_key_custody_safe_reference"]
        password = secrets.token_urlsafe(32)
        protected = await asyncio.to_thread(backup, password)
        restored = selected_members(protected, password)
        receipt["protected_core_archive_recovers_pair_key"] = restored[
            "data/.symphonia-key-custody-lab-v1/pair.key"] == key_bytes
        try:
            selected_members(protected, "incorrect-synthetic-backup-password")
        except (SecureTarError, tarfile.ReadError):
            receipt["wrong_backup_password_rejected"] = True
        else:
            receipt["wrong_backup_password_rejected"] = False
        assert all(value for name, value in receipt.items() if isinstance(value, bool) and name not in {
            "personal_or_provider_credentials", "core_restore_performed", "core_key_excluded_from_backup"})
        return receipt
    finally:
        cleanup = []
        for slug in created:
            try:
                await asyncio.to_thread(request, "/backups/" + slug, method="DELETE")
                cleanup.append(True)
            except Exception:
                cleanup.append(False)
        if reference_bytes is not None and REFERENCE.read_bytes() == reference_bytes:
            REFERENCE.unlink()
        if ((ROOT / ".owned").read_text() == MARKER and not ROOT.is_symlink()
                and {item.name for item in ROOT.iterdir()} <= {".owned", "pair.key"}):
            shutil.rmtree(ROOT)
        receipt["owned_backup_cleanup"] = all(cleanup)
        receipt["owned_core_files_removed"] = not ROOT.exists() and not REFERENCE.exists()
        await hass.async_stop()
        if not receipt["owned_backup_cleanup"] or not receipt["owned_core_files_removed"]:
            print(json.dumps({"owned_backup_cleanup": cleanup, "owned_backup_slugs": created,
                              "owned_core_files_removed": receipt["owned_core_files_removed"]}))
            raise RuntimeError("lab_cleanup_incomplete")


if __name__ == "__main__":
    try:
        print(json.dumps(asyncio.run(campaign()), sort_keys=True))
    except Exception as error:
        print(json.dumps({"mode": "core_key_backup_probe_failed", "exception_type": type(error).__name__}))
        raise SystemExit(1) from None
