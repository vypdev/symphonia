"""Synthetic test PKI provisioning and Core-to-Supervisor-App TLS experiment."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import ssl


ROOT = Path("/tmp/symphonia-oauth-companion-lab-fixture-v3")
ALIAS = "local-symphonia-oauth-lab-transport"
MARKER = "symphonia-synthetic-oauth-lab-v1"


def prepare():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    ROOT.mkdir(mode=0o700)  # Refuse an existing or symlinked fixture.
    (ROOT / ".owned").write_text(MARKER)
    out = ROOT / "app-data"
    excluded, included = out / "excluded", out / "included"
    excluded.mkdir(parents=True, mode=0o700)
    included.mkdir(mode=0o700)
    now = datetime.now(timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic lab CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    ca_bytes = ca.public_bytes(serialization.Encoding.PEM)
    (ROOT / "ca.crt").write_bytes(ca_bytes)
    (excluded / "ca.crt").write_bytes(ca_bytes)

    def leaf(name, server=False):
        key = ec.generate_private_key(ec.SECP256R1())
        cert = (x509.CertificateBuilder().subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, name)]))
            .issuer_name(ca_name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH if server else ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
        destination = excluded if server else ROOT
        stem = "server" if server else name
        key_bytes = key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        (destination / (stem + ".key")).write_bytes(key_bytes)
        os.chmod(destination / (stem + ".key"), 0o600)
        (destination / (stem + ".crt")).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        return hashlib.sha256(key.public_key().public_bytes(serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()

    server_pin = leaf(ALIAS, server=True)
    leaf("client")
    leaf("stranger")
    challenge = secrets.token_urlsafe(32)
    (excluded / "enrollment.json").write_text(json.dumps({"challenge": challenge}))
    master = secrets.token_bytes(32)
    (excluded / "wrapping.key").write_bytes(master)
    plain_canary = "SYNTHETIC-PAIR-CONTROL-" + secrets.token_hex(24)
    (included / "plaintext-control.json").write_text(json.dumps({"key": plain_canary}))
    secret = "SYNTHETIC-SEALED-KEY-" + secrets.token_hex(24)
    nonce = secrets.token_bytes(12)
    sealed = AESGCM(master).encrypt(nonce, secret.encode(), b"lab/oauth/pair/v1")
    (included / "sealed-record.json").write_text(json.dumps({
        "nonce": base64.b64encode(nonce).decode(), "ciphertext": base64.b64encode(sealed).decode()}))
    (ROOT / "private-checks.json").write_text(json.dumps({
        "server_pin": server_pin, "challenge": challenge, "plain_canary": plain_canary,
        "sealed_canary": secret, "master_b64": base64.b64encode(master).decode()}))
    for file in ROOT.rglob("*"):
        if file.is_file():
            os.chmod(file, 0o600)
    print(json.dumps({"fixture_prepared": True, "personal_or_provider_credentials": False}))


def probe():
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    assert (ROOT / ".owned").read_text() == MARKER
    private = json.loads((ROOT / "private-checks.json").read_text())
    receipt = {"mode": "actual_core_to_supervisor_app_tls", "real_spotify": "not_run"}

    def call(value, *, client="client", pin=None, path="/internal/ha-oauth/v1", method="POST"):
        context = ssl.create_default_context(cafile=str(ROOT / "ca.crt"))
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        if client:
            context.load_cert_chain(str(ROOT / (client + ".crt")), str(ROOT / (client + ".key")))
        conn = http.client.HTTPSConnection(ALIAS, 8098, timeout=5, context=context)
        try:
            conn.connect()
            certificate = x509.load_der_x509_certificate(conn.sock.getpeercert(binary_form=True))
            observed = hashlib.sha256(certificate.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()
            if observed != (pin or private["server_pin"]):
                return "pin_rejected_before_body"
            body = json.dumps(value).encode()
            conn.request(method, path, body, {"Content-Type": "application/json"})
            response = conn.getresponse()
            response.read(1024)
            return response.status
        finally:
            conn.close()

    base = {"version": 1, "profile": "oauth", "epoch": 0}
    hello = {**base, "op": "hello"}
    enroll = {**base, "op": "pair.enroll", "challenge": private["challenge"]}
    receipt["internal_alias_resolves"] = bool(socket.getaddrinfo(ALIAS, 8098))
    receipt["wrong_pin_before_enrollment"] = call(enroll, pin="0" * 64)
    receipt["unenrolled_client_status"] = call(hello)
    receipt["wrong_challenge_status"] = call({**enroll, "challenge": "incorrect"})
    receipt["enroll_status"] = call(enroll)
    receipt["replayed_enrollment_status"] = call(enroll)
    receipt["paired_mtls_status"] = call(hello)
    receipt["missing_client_cert_status"] = call(hello, client=None)
    receipt["other_signed_client_status"] = call(hello, client="stranger")
    receipt["wrong_epoch_status"] = call({**hello, "epoch": 9})
    receipt["wrong_version_status"] = call({**hello, "version": 2})
    receipt["playback_profile_status"] = call({**hello, "profile": "playback"})
    receipt["player_command_status"] = call({**base, "op": "player.command"})
    receipt["management_route_status"] = call(hello, path="/api/dashboard")
    receipt["get_management_status"] = call({}, path="/", method="GET")
    receipt["unknown_field_status"] = call({**hello, "url": "https://example.invalid"})
    receipt["revoke_status"] = call({**base, "op": "pair.revoke"})
    receipt["revoked_client_status"] = call(hello)
    expected = {"enroll_status", "paired_mtls_status", "revoke_status"}
    for name, value in receipt.items():
        if name.endswith("_status"):
            assert value == (200 if name in expected else 404 if name in {
                "management_route_status", "get_management_status"} else 400 if name == "unknown_field_status" else 403), name
    assert receipt["wrong_pin_before_enrollment"] == "pin_rejected_before_body"
    print(json.dumps(receipt, sort_keys=True))


def stalls():
    """Actual TLS handshake/header/body idle regressions; no pairing secret."""
    assert (ROOT / ".owned").read_text() == MARKER

    def connect(client=True):
        context = ssl.create_default_context(cafile=str(ROOT / "ca.crt"))
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        if client:
            context.load_cert_chain(str(ROOT / "client.crt"), str(ROOT / "client.key"))
        raw = socket.create_connection((ALIAS, 8098), timeout=5)
        try:
            return context.wrap_socket(raw, server_hostname=ALIAS)
        except BaseException:
            raw.close()
            raise

    def healthy():
        with connect() as connection:
            connection.sendall(b"GET / HTTP/1.1\r\nHost: fixture\r\n\r\n")
            response = http.client.HTTPResponse(connection)
            response.begin()
            assert response.status == 404
            response.read()

    receipt = {"mode": "actual_core_to_app_stall_regressions", "real_spotify": "not_run"}
    with socket.create_connection((ALIAS, 8098), timeout=5) as raw:
        assert raw.recv(1) == b""
    receipt["idle_real_tls_handshake_closed"] = True
    healthy()
    receipt["served_after_handshake_timeout"] = True
    for name, payload in (
        ("headers", b"POST /internal/ha-oauth/v1 HTTP/1.1\r\nHost: fixture\r\n"),
        ("body", b"POST /internal/ha-oauth/v1 HTTP/1.1\r\nHost: fixture\r\n"
         b"Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{"),
    ):
        with connect() as stalled:
            stalled.sendall(payload)
            healthy()
            assert stalled.recv(1) == b""
        receipt["served_after_" + name + "_timeout"] = True
    with connect(False) as connection:
        connection.sendall(b"POST /internal/ha-oauth/v1 HTTP/1.1\r\nHost: fixture\r\n"
                           b"Content-Type: application/json\r\nContent-Length: 100\r\n\r\n")
        response = http.client.HTTPResponse(connection)
        response.begin()
        assert response.status == 403
        response.read()
    receipt["missing_certificate_rejected_before_body"] = True
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "probe", "stalls"))
    args = parser.parse_args()
    try:
        {"prepare": prepare, "probe": probe, "stalls": stalls}[args.command]()
    except Exception as error:
        print(json.dumps({"probe": "failed", "exception_type": type(error).__name__,
            "tls_verify_code": getattr(error, "verify_code", None)}))
        raise SystemExit(1) from None
