"""Actual Supervisor backup experiment using only generated lab canaries.

Run in disposable Core after transport_probe prepare/probe. Only the research
App is restored; the running Core configuration is NEVER restored. Created
backup archives and the exact owned Core control file are removed in finally.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import tarfile
import time
import traceback
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


ROOT = Path("/tmp/symphonia-oauth-companion-lab-fixture-v3")
APP = "local_symphonia_oauth_lab_transport"
CONTROL = Path("/config/.storage/symphonia_oauth_lab_backup_control")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def run_probe():
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from securetar import SecureTarError, SecureTarFile

    assert (ROOT / ".owned").read_text() == "symphonia-synthetic-oauth-lab-v1"
    private = json.loads((ROOT / "private-checks.json").read_text())
    supervisor_token = os.environ["SUPERVISOR_TOKEN"]
    opener = build_opener(ProxyHandler({}), NoRedirect)
    created = []
    receipt = {"mode": "actual_supervisor_backups", "personal_or_provider_credentials": False,
        "core_restore_performed": False, "app_restore_only": True}

    def request(path, data=None, *, download=False, method=None):
        assert path.startswith("/backups/") or path.startswith("/addons/" + APP + "/")
        body = json.dumps(data).encode() if data is not None else None
        req = Request("http://supervisor" + path, data=body, method=method,
            headers={"Authorization": "Bearer " + supervisor_token,
                     "Content-Type": "application/json"})
        try:
            with opener.open(req, timeout=300) as response:
                raw = response.read(128 * 1024 * 1024 + 1 if download else 4 * 1024 * 1024)
        except HTTPError as error:
            error.close()
            raise RuntimeError("supervisor_operation_failed") from None
        if download:
            assert len(raw) <= 128 * 1024 * 1024, "backup_size_bound"
            return raw
        value = json.loads(raw)
        assert value.get("result") == "ok", "supervisor_result_not_ok"
        return value.get("data", {})

    def create(password=None):
        payload = {"name": "Symphonia synthetic OAuth key backup probe",
            "addons": [APP], "homeassistant": True,
            "homeassistant_exclude_database": True, "compressed": True}
        if password:
            payload["password"] = password
        result = request("/backups/new/partial", payload)
        slug = result["slug"]
        assert re.fullmatch(r"[a-f0-9]{1,64}", slug), "invalid_backup_slug"
        created.append(slug)
        archive = request("/backups/" + slug + "/download", download=True)
        return slug, archive

    def inspect_archive(archive, password=None):
        results = {}
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as outer:
            for member in outer:
                if member.name not in {APP + ".tar.gz", "homeassistant.tar.gz"}:
                    continue
                payload = outer.extractfile(member).read()
                selected = {}
                excluded = False
                with SecureTarFile(fileobj=io.BytesIO(payload), password=password) as inner:
                    for child in inner:
                        if "excluded/" in child.name:
                            excluded = True
                        if child.isfile() and child.name.endswith((
                            "included/plaintext-control.json", "included/sealed-record.json",
                            ".storage/symphonia_oauth_lab_backup_control")):
                            assert child.size < 16384, "canary_file_size"
                            selected[child.name] = inner.extractfile(child).read()
                results[member.name] = {"selected": selected, "excluded": excluded}
        assert set(results) == {APP + ".tar.gz", "homeassistant.tar.gz"}, "backup_members_missing"
        return results

    canary = "SYNTHETIC-CORE-KEY-CONTROL-" + secrets.token_hex(24)
    control_bytes = json.dumps({"version": 1, "key": "symphonia_oauth_lab_backup_control",
        "data": {"canary": canary}}).encode()
    descriptor = os.open(CONTROL, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(control_bytes)
    try:
        plain_slug, unprotected = create()
        plain = inspect_archive(unprotected)
        app_files = plain[APP + ".tar.gz"]["selected"]
        core_files = plain["homeassistant.tar.gz"]["selected"]
        receipt["unprotected_core_backup_contains_plaintext_control"] = any(
            canary.encode() in content for content in core_files.values())
        receipt["unprotected_app_backup_contains_plaintext_control"] = any(
            private["plain_canary"].encode() in content for content in app_files.values())
        receipt["app_backup_excludes_key_directory"] = not plain[APP + ".tar.gz"]["excluded"]
        sealed_raw = next(content for name, content in app_files.items() if name.endswith("sealed-record.json"))
        sealed = json.loads(sealed_raw)
        nonce = base64.b64decode(sealed["nonce"])
        ciphertext = base64.b64decode(sealed["ciphertext"])
        master = base64.b64decode(private["master_b64"])
        aad = b"lab/oauth/pair/v1"
        receipt["sealed_backup_restores_with_external_key"] = AESGCM(master).decrypt(
            nonce, ciphertext, aad).decode() == private["sealed_canary"]
        receipt["sealed_record_contains_no_plaintext_key"] = private["sealed_canary"].encode() not in sealed_raw
        for name, key, data, associated in (
            ("wrong_key_rejected", secrets.token_bytes(32), ciphertext, aad),
            ("tampered_record_rejected", master, ciphertext[:-1] + bytes([ciphertext[-1] ^ 1]), aad),
            ("wrong_profile_binding_rejected", master, ciphertext, b"lab/playback/pair/v1"),
        ):
            try:
                AESGCM(key).decrypt(nonce, data, associated)
            except InvalidTag:
                receipt[name] = True
            else:
                receipt[name] = False

        password = secrets.token_urlsafe(32)
        _, protected = create(password)
        restored = inspect_archive(protected, password)
        receipt["protected_backup_decrypts_with_password"] = any(
            canary.encode() in content for content in restored["homeassistant.tar.gz"]["selected"].values())
        try:
            inspect_archive(protected, "incorrect-synthetic-backup-password")
        except (SecureTarError, tarfile.ReadError):
            receipt["protected_backup_wrong_password_rejected"] = True
        else:
            receipt["protected_backup_wrong_password_rejected"] = False

        # Restore exclusively the synthetic App; Core data/auth is not restored.
        request("/backups/" + plain_slug + "/restore/partial",
                {"addons": [APP], "homeassistant": False})
        # Query only state, not the full metadata response in ordinary evidence.
        info = request("/addons/" + APP + "/info")
        for _ in range(10):
            if info.get("state") != "started":
                break
            time.sleep(1)
            info = request("/addons/" + APP + "/info")
        receipt["restored_app_not_running"] = info.get("state") != "started"
        receipt["backup_archive_bytes"] = {"unprotected": len(unprotected), "protected": len(protected)}
        assert all(value for name, value in receipt.items() if isinstance(value, bool)
                   and name not in {"personal_or_provider_credentials", "core_restore_performed"}), "backup_contract_failed"
        return receipt
    finally:
        # Exact owned canary only; never touch the actual auth/config files.
        if CONTROL.exists() and hashlib.sha256(CONTROL.read_bytes()).digest() == hashlib.sha256(control_bytes).digest():
            CONTROL.unlink()
        cleanup = []
        for slug in created:
            try:
                request("/backups/" + slug, {}, method="DELETE")
                cleanup.append(True)
            except Exception:
                cleanup.append(False)
        print(json.dumps({"created_backup_cleanup": cleanup, "core_control_removed": not CONTROL.exists()}))
        if not all(cleanup) or CONTROL.exists():
            raise RuntimeError("owned_lab_backup_cleanup_incomplete")


if __name__ == "__main__":
    try:
        print(json.dumps(run_probe(), sort_keys=True))
    except Exception as error:
        print(json.dumps({"probe": "failed", "exception_type": type(error).__name__,
            "location": [{"function": frame.name, "line": frame.lineno}
                         for frame in traceback.extract_tb(error.__traceback__)[-3:]]}))
        raise SystemExit(1) from None
