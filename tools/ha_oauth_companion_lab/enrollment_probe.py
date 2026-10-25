"""Synthetic CSR issuance/recovery research, never a production integration.

Only a fresh owned /data/csr-lab as UID 10001 is accepted by the campaign.
Real cryptography and loopback TLS supplement, rather than replace, the earlier
Core-to-Supervisor topology proof. No HA/provider credential or host port.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import secrets
import sqlite3
import ssl
import subprocess
import sys
import threading
import time

from tools.ha_oauth_companion_lab.key_custody_probe import Locked, PrivateFiles, encoded


MARKER = "symphonia-synthetic-csr-lifecycle-v1"


def crypto():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    return x509, hashes, serialization, ec, ExtendedKeyUsageOID, NameOID


def fingerprint(key):
    _, _, serialization, *_ = crypto()
    return hashlib.sha256(key.public_bytes(serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()


def private(key):
    _, _, serialization, *_ = crypto()
    return key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def client():
    x509, hashes, serialization, ec, _, _ = crypto()
    key = ec.generate_private_key(ec.SECP256R1())
    csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([])).sign(key, hashes.SHA256())
    return key, csr.public_bytes(serialization.Encoding.PEM).decode()


def renewal_payload(der, epoch, csr):
    """Domain-separated intent; public certificate possession is not authority."""
    if (not isinstance(der,bytes) or not 0<len(der)<=8192 or type(epoch) is not int
            or not 0<=epoch<2**63 or not isinstance(csr,str) or not 0<len(csr)<=8192):
        raise Locked("renewal_binding_refused")
    return encoded({"domain":"symphonia-csr-renewal-v1","epoch":epoch,
        "certificate_sha256":hashlib.sha256(der).hexdigest(),
        "csr_sha256":hashlib.sha256(csr.encode()).hexdigest()})


def renewal_proof(key, der, epoch, csr):
    _,hashes,_,ec,*_=crypto()
    return base64.b64encode(key.sign(renewal_payload(der,epoch,csr),ec.ECDSA(hashes.SHA256()))).decode()


class Issuer:
    def __init__(self, root, *, clock=time.time):
        self.root, self.clock = root, clock
        with PrivateFiles(root) as files:
            if json.loads(files.read("owned.json")) != {"marker": MARKER}:
                raise Locked("unowned_csr_fixture")
            raw = files.read("ca.key", 8192)
            files.read("state.sqlite", 1048576)
        x509, _, serialization, *_ = crypto()
        self.key = serialization.load_pem_private_key(raw, password=None)
        self.db = sqlite3.connect(root / "state.sqlite", isolation_level=None, check_same_thread=False)
        self.db.execute("PRAGMA synchronous=FULL")
        self.lock = threading.RLock()

    def close(self):
        self.db.close()

    @classmethod
    def create(cls, root):
        x509, hashes, serialization, ec, eku, names = crypto()
        root.mkdir(mode=0o700)
        now = datetime.now(timezone.utc)
        ca_key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(names.COMMON_NAME, "Synthetic CSR issuer")])
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
              .not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(True, 0), True)
              .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), True)
              .sign(ca_key, hashes.SHA256()))
        server_key = ec.generate_private_key(ec.SECP256R1())
        server = (x509.CertificateBuilder().subject_name(x509.Name([])).issuer_name(name)
              .public_key(server_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=1))
              .add_extension(x509.BasicConstraints(False, None), True)
              .add_extension(x509.SubjectAlternativeName([x509.DNSName("csr-lab")]), False)
              .add_extension(x509.ExtendedKeyUsage([eku.SERVER_AUTH]), False)
              .sign(ca_key, hashes.SHA256()))
        with PrivateFiles(root) as files:
            for path, value in {"owned.json": encoded({"marker": MARKER}), "ca.key": private(ca_key),
                "ca.crt": ca.public_bytes(serialization.Encoding.PEM), "server.key": private(server_key),
                "server.crt": server.public_bytes(serialization.Encoding.PEM)}.items():
                files.publish(path, value, exclusive=True)
        db = sqlite3.connect(root / "state.sqlite")
        os.chmod(root / "state.sqlite", 0o600)
        try:
            db.executescript("CREATE TABLE pair(singleton INTEGER PRIMARY KEY,epoch INTEGER,serial TEXT,peer TEXT);"
                "INSERT INTO pair VALUES(1,0,NULL,NULL);"
                "CREATE TABLE challenge(singleton INTEGER PRIMARY KEY,digest TEXT,deadline REAL,failures INTEGER);"
                "CREATE TABLE issuance(id TEXT PRIMARY KEY,epoch INTEGER,csr TEXT,certificate TEXT,parent_serial TEXT);")
            db.commit()
        finally:
            db.close()
        return cls(root)

    def challenge(self):
        with self.lock:
            if self.db.execute("SELECT peer FROM pair").fetchone()[0] is not None:
                raise Locked("already_paired")
            if self.db.execute("SELECT COUNT(*) FROM issuance WHERE certificate IS NULL AND epoch=(SELECT epoch FROM pair)").fetchone()[0]:
                raise Locked("issuance_resume_required")
            value = secrets.token_urlsafe(32)
            self.db.execute("INSERT OR REPLACE INTO challenge VALUES(1,?,?,0)",
                (hashlib.sha256(value.encode()).hexdigest(), self.clock()+300))
            return value

    @staticmethod
    def validate_csr(raw):
        x509, hashes, _, ec, *_ = crypto()
        if not isinstance(raw, str) or len(raw.encode()) > 8192:
            raise Locked("bounded_csr_required")
        try:
            csr = x509.load_pem_x509_csr(raw.encode())
            key = csr.public_key()
            if (not csr.is_signature_valid or not isinstance(key, ec.EllipticCurvePublicKey)
                    or not isinstance(key.curve, ec.SECP256R1)
                    or not isinstance(csr.signature_hash_algorithm, hashes.SHA256)
                    or len(csr.extensions) or len(csr.subject)):
                raise ValueError
            return csr
        except Exception:
            raise Locked("csr_refused") from None

    def enroll(self, challenge, csr, *, checkpoint=lambda point: None):
        self.validate_csr(csr)
        if not isinstance(challenge, str) or len(challenge) > 128:
            raise Locked("challenge_refused")
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute("SELECT digest,deadline,failures FROM challenge").fetchone()
                epoch, peer = self.db.execute("SELECT epoch,peer FROM pair").fetchone()
                if (not row or peer is not None or self.clock() >= row[1] or row[2] >= 5
                        or not hmac.compare_digest(row[0], hashlib.sha256(challenge.encode()).hexdigest())):
                    if row:
                        self.db.execute("UPDATE challenge SET failures=MIN(failures+1,5)")
                    self.db.commit()
                    raise Locked("challenge_refused")
                receipt = secrets.token_hex(16)
                self.db.execute("DELETE FROM challenge")
                self.db.execute("INSERT INTO issuance VALUES(?,?,?,NULL,NULL)", (receipt, epoch, csr))
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise
            checkpoint("issuance_admitted")
            return receipt, self.resume(receipt, checkpoint=checkpoint)

    def renew(self, der, epoch, csr, *, proof=None, checkpoint=lambda point: None):
        self.validate_csr(csr)
        # Also enforce possession here, independent of the mTLS adapter. An
        # observed public cert/signature cannot authorize a different CSR or epoch.
        try:
            if not isinstance(proof,str) or not 0<len(proof)<=256:
                raise ValueError
            signature=base64.b64decode(proof,validate=True)
            x509,hashes,_,ec,*_=crypto()
            key=x509.load_der_x509_certificate(der).public_key()
            key.verify(signature,renewal_payload(der,epoch,csr),ec.ECDSA(hashes.SHA256()))
        except Exception:
            raise Locked("renewal_possession_required") from None
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if not self.accepts(der, epoch):
                    raise Locked("renewal_peer_refused")
                serial = self.db.execute("SELECT serial FROM pair").fetchone()[0]
                receipt = secrets.token_hex(16)
                self.db.execute("INSERT INTO issuance VALUES(?,?,?,NULL,?)", (receipt, epoch, csr, serial))
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise
            checkpoint("issuance_admitted")
            return receipt, self.resume(receipt, checkpoint=checkpoint)

    def status(self, receipt):
        # Public certificate/result only; this read cannot mint a certificate.
        with self.lock:
            row = self.db.execute("SELECT certificate FROM issuance WHERE id=?", (receipt,)).fetchone()
            return row[0] if row else None

    def resume(self, receipt, *, checkpoint=lambda point: None):
        x509, hashes, serialization, _, eku, names = crypto()
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute("SELECT epoch,csr,certificate,parent_serial FROM issuance WHERE id=?", (receipt,)).fetchone()
                if not row:
                    raise Locked("unknown_issuance")
                if row[2]:
                    self.db.commit()
                    return row[2]
                epoch, peer, serial = self.db.execute("SELECT epoch,peer,serial FROM pair").fetchone()
                if epoch != row[0] or (peer is not None and serial != row[3]) or (peer is None and row[3] is not None):
                    raise Locked("issuance_fenced")
                csr = self.validate_csr(row[1])
                now = datetime.fromtimestamp(self.clock(), timezone.utc)
                cert = (x509.CertificateBuilder().subject_name(x509.Name([]))
                    .issuer_name(x509.Name([x509.NameAttribute(names.COMMON_NAME, "Synthetic CSR issuer")]))
                    .public_key(csr.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now-timedelta(seconds=30)).not_valid_after(now+timedelta(minutes=10))
                    .add_extension(x509.BasicConstraints(False, None), True)
                    .add_extension(x509.ExtendedKeyUsage([eku.CLIENT_AUTH]), False)
                    .sign(self.key, hashes.SHA256()))
                pem = cert.public_bytes(serialization.Encoding.PEM).decode()
                self.db.execute("UPDATE pair SET serial=?,peer=?", (str(cert.serial_number), fingerprint(csr.public_key())))
                self.db.execute("UPDATE issuance SET certificate=? WHERE id=?", (pem, receipt))
                checkpoint("before_issue_commit")
                self.db.commit()
                checkpoint("after_issue_commit")
                return pem
            except BaseException:
                self.db.rollback()
                raise

    def accepts(self, der, epoch=0, profile="oauth"):
        x509, _, serialization, *_ = crypto()
        if not isinstance(der,bytes) or not 0<len(der)<=8192 or profile != "oauth" or type(epoch) is not int:
            return False
        cert = x509.load_der_x509_certificate(der)
        with self.lock:
            current, serial, peer = self.db.execute("SELECT epoch,serial,peer FROM pair").fetchone()
            issued=self.db.execute("SELECT certificate FROM issuance WHERE epoch=? AND certificate IS NOT NULL",(current,)).fetchall()
            exact_issued=any(hmac.compare_digest(der,x509.load_pem_x509_certificate(row[0].encode()).public_bytes(serialization.Encoding.DER)) for row in issued)
        return (exact_issued and current == epoch and serial == str(cert.serial_number) and peer == fingerprint(cert.public_key())
                and cert.not_valid_before_utc.timestamp() <= self.clock() < cert.not_valid_after_utc.timestamp())

    def revoke(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("UPDATE pair SET epoch=epoch+1,serial=NULL,peer=NULL")
                self.db.execute("DELETE FROM challenge")
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise


def campaign(root):
    if root != Path("/data/csr-lab") or os.geteuid() != 10001:
        raise Locked("wrong_disposable_context")
    issuer = Issuer.create(root)
    results = {}
    x509, hashes, serialization, ec, _, _ = crypto()
    key, csr = client()
    challenge = issuer.challenge()
    for label, bad in (("wrong_challenge", "incorrect"),):
        try:
            issuer.enroll(bad, csr)
        except Locked:
            results[label] = issuer.db.execute("SELECT COUNT(*) FROM issuance").fetchone()[0] == 0
        else:
            raise AssertionError(label)
    receipt, pem = issuer.enroll(challenge, csr)
    cert = x509.load_pem_x509_certificate(pem.encode())
    der = cert.public_bytes(serialization.Encoding.DER)
    results["public_certificate_matches_csr_key"] = fingerprint(cert.public_key()) == fingerprint(key.public_key())
    results["issued_identity_active"] = issuer.accepts(der)
    results["status_does_not_reissue"] = issuer.status(receipt) == pem and issuer.resume(receipt) == pem
    try:
        issuer.enroll(challenge, csr)
    except Locked:
        results["enrollment_replay_refused"] = True
    else:
        raise AssertionError("replay")
    results["wrong_epoch_refused"] = not issuer.accepts(der, 9)
    results["playback_authority_refused"] = not issuer.accepts(der, profile="playback")
    results["no_peer_refused"] = not issuer.accepts(None)
    issuer.close()
    issuer = Issuer(root)
    results["durable_pair_and_ca_reopen"] = issuer.accepts(der) and issuer.status(receipt) == pem
    renewed_key, renewed_csr = client()
    proof=renewal_proof(key,der,0,renewed_csr)
    attacker,_=client()
    for label,request_csr,request_epoch,request_proof in (
        ("public_certificate_alone_cannot_renew",renewed_csr,0,None),
        ("attacker_key_cannot_sign_renewal",renewed_csr,0,renewal_proof(attacker,der,0,renewed_csr)),
        ("renewal_signature_binds_replacement_csr",csr,0,proof),
        ("renewal_signature_binds_epoch",renewed_csr,1,proof),
        ("malformed_renewal_signature_refused",renewed_csr,0,"not-base64!")):
        before=issuer.db.execute("SELECT COUNT(*) FROM issuance").fetchone()[0]
        try:issuer.renew(der,request_epoch,request_csr,proof=request_proof)
        except Locked:
            results[label]=issuer.accepts(der) and issuer.db.execute("SELECT COUNT(*) FROM issuance").fetchone()[0]==before
        else:raise AssertionError(label)
    substituted=bytearray(der);substituted[-1]^=1;substituted=bytes(substituted)
    try:issuer.renew(substituted,0,renewed_csr,proof=renewal_proof(key,substituted,0,renewed_csr))
    except Locked:results["substituted_issuer_signature_cannot_renew"]=issuer.accepts(der)
    else:raise AssertionError("unissued_certificate")
    renewed_receipt, renewed_pem = issuer.renew(der, 0, renewed_csr,proof=proof)
    renewed_der = x509.load_pem_x509_certificate(renewed_pem.encode()).public_bytes(serialization.Encoding.DER)
    results["renewal_switches_exact_identity"] = issuer.accepts(renewed_der) and not issuer.accepts(der)
    results["renewal_lost_ack_is_stable"] = issuer.resume(renewed_receipt) == renewed_pem
    key, pem, der = renewed_key, renewed_pem, renewed_der
    tls_results = tls_probe(root, issuer, key, pem, der)
    results.update(tls_results)
    issuer.revoke()
    results["revocation_fences_certificate"] = not issuer.accepts(der)
    challenge = issuer.challenge()
    key2, csr2 = client()
    receipt2, pem2 = issuer.enroll(challenge, csr2)
    der2 = x509.load_pem_x509_certificate(pem2.encode()).public_bytes(serialization.Encoding.DER)
    results["explicit_repair_new_epoch"] = issuer.accepts(der2, 1) and not issuer.accepts(der, 1)
    original_clock = issuer.clock
    issuer.clock = lambda: original_clock()+601
    results["expired_certificate_refused"] = not issuer.accepts(der2, 1)
    issuer.clock = original_clock
    issuer.revoke()
    challenge = issuer.challenge()
    issuer.clock = lambda: original_clock()+301
    try:
        issuer.enroll(challenge, csr)
    except Locked:
        results["expired_challenge_refused"] = True
    else:
        raise AssertionError("expired_challenge")
    issuer.clock = original_clock
    hostile = (x509.CertificateSigningRequestBuilder().subject_name(x509.Name([]))
        .add_extension(x509.BasicConstraints(True, None), True).sign(key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM).decode())
    weak_key = ec.generate_private_key(ec.SECP384R1())
    weak = (x509.CertificateSigningRequestBuilder().subject_name(x509.Name([])).sign(weak_key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM).decode())
    damaged = bytearray(x509.load_pem_x509_csr(csr.encode()).public_bytes(serialization.Encoding.DER))
    damaged[-1] ^= 1
    invalid = "-----BEGIN CERTIFICATE REQUEST-----\n"+base64.b64encode(damaged).decode()+"\n-----END CERTIFICATE REQUEST-----\n"
    from cryptography.x509.oid import NameOID
    subject = (x509.CertificateSigningRequestBuilder().subject_name(x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME,"caller-selected-authority")])).sign(key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM).decode())
    for label, value in (("csr_extension_refused", hostile), ("wrong_curve_refused", weak),
                         ("csr_subject_refused",subject), ("invalid_csr_signature_refused", invalid),
                         ("oversized_csr_refused", "x"*8193)):
        try:
            issuer.validate_csr(value)
        except Locked:
            results[label] = True
        else:
            raise AssertionError(label)
    results["ca_key_private_0600"] = (root/"ca.key").stat().st_mode & 0o777 == 0o600
    limited = issuer.challenge()
    for _ in range(5):
        try:
            issuer.enroll("wrong",csr)
        except Locked:
            pass
        else:
            raise AssertionError("wrong_challenge_accepted")
    try:
        issuer.enroll(limited,csr)
    except Locked:
        results["per_challenge_failure_budget"] = True
    else:
        raise AssertionError("failure_budget_ignored")
    for point in ("issuance_admitted","before_issue_commit","after_issue_commit"):
        challenge = issuer.challenge()
        _, pending_csr = client()
        epoch = issuer.db.execute("SELECT epoch FROM pair").fetchone()[0]
        completed = subprocess.run([sys.executable, __file__, "--root", str(root), "--child", "--point", point],
            input=encoded({"challenge": challenge, "csr": pending_csr}), stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=15,
            env={"PATH":os.environ.get("PATH", ""), "PYTHONPATH":"/research", "PYTHONDONTWRITEBYTECODE":"1"})
        assert completed.returncode == 83
        issued = issuer.db.execute("SELECT id FROM issuance WHERE epoch=?",(epoch,)).fetchall()
        assert len(issued) == 1
        pending_id = issued[0][0]
        issuer.close()
        issuer = Issuer(root)
        before = issuer.status(pending_id)
        assert (before is not None) == (point=="after_issue_commit")
        if before is None:
            assert issuer.db.execute("SELECT peer FROM pair").fetchone()[0] is None
            try:
                issuer.challenge()
            except Locked:
                pass
            else:
                raise AssertionError("pending_issuance_replaced")
            assert issuer.status(pending_id) is None
        resumed = issuer.resume(pending_id)
        resumed_der = x509.load_pem_x509_certificate(resumed.encode()).public_bytes(serialization.Encoding.DER)
        results["process_death_"+point] = issuer.accepts(resumed_der,epoch) and issuer.resume(pending_id)==resumed
        issuer.revoke()
    issuer.close()
    # Existing identity loss is locked; opening never mints a replacement CA.
    (root/"ca.key").unlink()
    try:
        Issuer(root)
    except Locked:
        results["missing_ca_key_locks_without_rekey"] = not (root/"ca.key").exists()
    else:
        raise AssertionError("missing_ca_key")
    assert all(results.values()), [name for name, value in results.items() if not value]
    return {"mode": "synthetic_csr_lifecycle", "results": results, "uid": os.geteuid(),
            "real_ha_or_provider": False, "wire_enrollment_renewal_or_ingress_reset_proven": False}


def tls_probe(root, issuer, key, pem, der):
    """A newly CSR-issued certificate, not pre-issued test PKI, crosses TLS."""
    from tools.ha_oauth_companion_lab.app.server import BoundedTLSHTTPServer

    class Verifier:
        def __init__(self):
            self.calls = 0
        def request(self, value, peer):
            self.calls += 1
            return 200 if (type(value.get("version")) is int and type(value.get("epoch")) is int
                and peer == hashlib.sha256(der).digest() and issuer.accepts(der)
                and value == {"op":"hello", "version":1, "profile":"oauth", "epoch":0}) else 403

    with PrivateFiles(root) as files:
        files.publish("core-client.key", private(key), exclusive=True)
        files.publish("core-client.crt", pem.encode(), exclusive=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(str(root/"server.crt"), str(root/"server.key"))
    context.load_verify_locations(str(root/"ca.crt"))
    context.verify_mode = ssl.CERT_OPTIONAL
    policy = Verifier()
    class ProbeServer(BoundedTLSHTTPServer):
        error_types = None
        def handle_error(self, request, client_address):
            self.error_types.append(type(sys.exception()).__name__)
    server = ProbeServer(("127.0.0.1", 0), context, policy)
    server.error_types = []
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    x509, *_ = crypto()
    server_pin = fingerprint(x509.load_pem_x509_certificate((root/"server.crt").read_bytes()).public_key())
    def call(*, pin=server_pin, certificate=True):
        client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client_context.minimum_version = ssl.TLSVersion.TLSv1_3
        client_context.check_hostname = False
        # The manually compared SPKI pin is the sole bootstrap trust anchor.
        client_context.verify_mode = ssl.CERT_NONE
        if certificate:
            client_context.load_cert_chain(str(root/"core-client.crt"), str(root/"core-client.key"))
        connection = http.client.HTTPSConnection("127.0.0.1", server.server_port, context=client_context, timeout=4)
        try:
            connection.connect()
            observed = fingerprint(x509.load_der_x509_certificate(connection.sock.getpeercert(binary_form=True)).public_key())
            if observed != pin:
                return "pin_refused_before_body"
            body = encoded({"op":"hello", "version":1, "profile":"oauth", "epoch":0})
            connection.request("POST", "/internal/ha-oauth/v1", body, {"Content-Type":"application/json"})
            response = connection.getresponse()
            response.read(1024)
            return response.status
        finally:
            connection.close()
    try:
        results = {"wrong_pin_before_request": call(pin="0"*64) == "pin_refused_before_body" and policy.calls == 0,
                   "csr_issued_client_crosses_actual_mtls": call() == 200,
                   "missing_client_certificate_denied": call(certificate=False) == 403}
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
    assert not worker.is_alive()
    results["no_unexpected_tls_error"] = set(server.error_types) <= {"BrokenPipeError", "ConnectionResetError", "SSLEOFError"}
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/data/csr-lab"))
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--point", default="issuance_admitted",choices=("issuance_admitted","before_issue_commit","after_issue_commit"))
    args = parser.parse_args()
    try:
        if args.child:
            payload = json.load(sys.stdin)
            issuer = Issuer(args.root)
            def checkpoint(point):
                if point == args.point:
                    os._exit(83)
            issuer.enroll(payload["challenge"], payload["csr"], checkpoint=checkpoint)
            raise AssertionError("child_did_not_die")
        print(json.dumps(campaign(args.root), sort_keys=True))
    except Exception as error:
        print(json.dumps({"mode": "csr_probe_failed", "exception_type": type(error).__name__}))
        raise SystemExit(1) from None
