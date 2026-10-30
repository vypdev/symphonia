"""Finite P-256 CA, pinned server and generated Core CSR enrollment."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import ssl

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .keys import PrivateFiles
from .policy import TrialError

PURPOSE = "symphonia-native-oauth-trial"


def spki(public) -> str:
    return hashlib.sha256(public.public_bytes(serialization.Encoding.DER,
                                              serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()


def pem_key(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def certificate(key, subject, issuer, public, started, deadline, *, ca=False, usage=None):
    builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(public)
               .serial_number(x509.random_serial_number())
               .not_valid_before(datetime.fromtimestamp(started, timezone.utc) - timedelta(seconds=5))
               .not_valid_after(datetime.fromtimestamp(deadline, timezone.utc))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=0 if ca else None), critical=True))
    if usage is not None:
        builder = builder.add_extension(x509.ExtendedKeyUsage([usage]), critical=True)
    return builder.sign(key, hashes.SHA256())


def provision(root: Path, installation: str, started: int, deadline: int):
    """Called only by an explicit empty-namespace provision, never by recovery."""
    ca_key, server_key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, installation + "-trial-ca")])
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, installation + "-trial-server")])
    ca = certificate(ca_key, issuer, issuer, ca_key.public_key(), started, deadline, ca=True)
    server = certificate(ca_key, subject, issuer, server_key.public_key(), started, deadline,
                         usage=ExtendedKeyUsageOID.SERVER_AUTH)
    with PrivateFiles(root) as files:
        for name, value in (("ca.key", pem_key(ca_key)), ("ca.crt", ca.public_bytes(serialization.Encoding.PEM)),
                            ("server.key", pem_key(server_key)), ("server.crt", server.public_bytes(serialization.Encoding.PEM)),
                            ("wrapping.key", os.urandom(32))):
            files.create(name, value)


def fd_path(fd):
    return f"/proc/self/fd/{fd}" if Path("/proc/self/fd").is_dir() else f"/dev/fd/{fd}"


class Authority:
    def __init__(self, root: Path, installation: str, deadline: int):
        self.root, self.installation, self.deadline = root, installation, deadline
        try:
            with PrivateFiles(root) as files:
                ca_raw, server_raw = files.read("ca.crt"), files.read("server.crt")
                ca_key = serialization.load_pem_private_key(files.read("ca.key"), None)
                server_key = serialization.load_pem_private_key(files.read("server.key"), None)
                if len(files.read("wrapping.key", 32)) != 32:
                    raise TrialError("locked")
            self.ca, self.server = x509.load_pem_x509_certificate(ca_raw), x509.load_pem_x509_certificate(server_raw)
            if (not isinstance(ca_key, ec.EllipticCurvePrivateKey) or not isinstance(server_key, ec.EllipticCurvePrivateKey)
                    or spki(ca_key.public_key()) != spki(self.ca.public_key())
                    or spki(server_key.public_key()) != spki(self.server.public_key())
                    or self.server.subject != x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, installation + "-trial-server")])
                    or int(self.ca.not_valid_after_utc.timestamp()) != deadline
                    or int(self.server.not_valid_after_utc.timestamp()) != deadline):
                raise TrialError("locked")
            self.ca.public_key().verify(self.server.signature, self.server.tbs_certificate_bytes,
                                         ec.ECDSA(self.server.signature_hash_algorithm))
            self.pin = spki(self.server.public_key())
            self.ca_pem = ca_raw.decode("ascii")
        except (ValueError, TypeError, OSError, InvalidSignature):
            raise TrialError("locked") from None

    def context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        try:
            with PrivateFiles(self.root) as files, files.descriptor("server.crt") as cert, files.descriptor("server.key") as key:
                context.load_cert_chain(fd_path(cert), fd_path(key))
            context.load_verify_locations(cadata=self.ca_pem)
            # Only enrollment lacks a client cert; all other operations check its pin.
            context.verify_mode = ssl.CERT_OPTIONAL
            return context
        except (ssl.SSLError, OSError):
            raise TrialError("locked") from None

    def csr(self, raw: str, actor: str):
        try:
            csr = x509.load_pem_x509_csr(raw.encode("ascii"))
            public = csr.public_key()
            expected = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, PURPOSE),
                                 x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, self.installation),
                                 x509.NameAttribute(NameOID.COMMON_NAME, actor)])
            if (not csr.is_signature_valid or csr.subject != expected or len(csr.extensions)
                    or not isinstance(public, ec.EllipticCurvePublicKey) or not isinstance(public.curve, ec.SECP256R1)):
                raise TrialError("tls_identity")
            return public
        except (ValueError, TypeError, UnicodeError):
            raise TrialError("tls_identity") from None

    def issue(self, public, pair_id: str, started: int):
        try:
            with PrivateFiles(self.root) as files:
                ca_key = serialization.load_pem_private_key(files.read("ca.key"), None)
            if spki(ca_key.public_key()) != spki(self.ca.public_key()):
                raise TrialError("locked")
            subject = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, PURPOSE),
                                 x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, self.installation),
                                 x509.NameAttribute(NameOID.COMMON_NAME, pair_id)])
            result = certificate(ca_key, subject, self.ca.subject, public, started, self.deadline,
                                  usage=ExtendedKeyUsageOID.CLIENT_AUTH)
            return result.public_bytes(serialization.Encoding.PEM).decode("ascii")
        except (ValueError, TypeError):
            raise TrialError("locked") from None

    def validate_request(self, raw, actor):
        return spki(self.csr(raw, actor))

    def issue_request(self, raw, actor, pair_id, started):
        return {"ca": self.ca_pem, "certificate": self.issue(self.csr(raw, actor), pair_id, started)}
