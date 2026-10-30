"""Core's narrowly scoped private pairing material; no Home Assistant dependency."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import ssl
import stat

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

PURPOSE = "symphonia-native-oauth-trial"


class KeyUnavailable(Exception):
    def __init__(self):
        super().__init__("pair_key_unavailable")


def spki(public):
    return hashlib.sha256(public.public_bytes(serialization.Encoding.DER,
                                              serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()


class CoreKeys:
    def __init__(self, root: Path):
        self.root = root

    @contextmanager
    def descriptor(self, name):
        directory = fd = None
        try:
            if name not in {"core.key", "ca.crt", "client.crt"}:
                raise KeyUnavailable
            directory = os.open(self.root, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY)
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise KeyUnavailable
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or not 0 < info.st_size <= 8192):
                raise KeyUnavailable
            yield fd
        except OSError:
            raise KeyUnavailable from None
        finally:
            if fd is not None:
                os.close(fd)
            if directory is not None:
                os.close(directory)

    def read(self, name):
        with self.descriptor(name) as fd:
            raw = os.read(fd, 8193)
            if len(raw) != os.fstat(fd).st_size or len(raw) > 8192:
                raise KeyUnavailable
            return raw

    def _create(self, name, raw):
        directory = fd = None
        try:
            directory = os.open(self.root, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY)
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise KeyUnavailable
            fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            pending = memoryview(raw)
            while pending:
                size = os.write(fd, pending)
                if size <= 0:
                    raise KeyUnavailable
                pending = pending[size:]
            os.fsync(fd); os.fsync(directory)
        except OSError:
            raise KeyUnavailable from None
        finally:
            if fd is not None:
                os.close(fd)
            if directory is not None:
                os.close(directory)

    def create_csr(self, installation, actor):
        try:
            self.root.mkdir(mode=0o700)  # An existing namespace is never rekeyed.
            key = ec.generate_private_key(ec.SECP256R1())
            self._create("core.key", key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            subject = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, PURPOSE),
                                 x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, installation),
                                 x509.NameAttribute(NameOID.COMMON_NAME, actor)])
            return x509.CertificateSigningRequestBuilder().subject_name(subject).sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode("ascii")
        except (OSError, ValueError):
            raise KeyUnavailable from None

    def accept(self, ca_pem, client_pem, *, installation, pair_id, deadline, server_der):
        try:
            ca, client = x509.load_pem_x509_certificate(ca_pem.encode("ascii")), x509.load_pem_x509_certificate(client_pem.encode("ascii"))
            server = x509.load_der_x509_certificate(server_der)
            key = serialization.load_pem_private_key(self.read("core.key"), None)
            expected = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, PURPOSE),
                                 x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, installation),
                                 x509.NameAttribute(NameOID.COMMON_NAME, pair_id)])
            if (spki(key.public_key()) != spki(client.public_key()) or client.subject != expected
                    or not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
                    or client.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
                    or list(client.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value) != [ExtendedKeyUsageOID.CLIENT_AUTH]
                    or int(client.not_valid_after_utc.timestamp()) != deadline
                    or int(ca.not_valid_after_utc.timestamp()) != deadline
                    or int(server.not_valid_after_utc.timestamp()) != deadline
                    or client.issuer != ca.subject or server.issuer != ca.subject
                    or datetime.now(timezone.utc) >= client.not_valid_after_utc):
                raise KeyUnavailable
            for cert in (client, server):
                ca.public_key().verify(cert.signature, cert.tbs_certificate_bytes, ec.ECDSA(cert.signature_hash_algorithm))
            self._create("ca.crt", ca_pem.encode("ascii"))
            self._create("client.crt", client_pem.encode("ascii"))
        except (ValueError, TypeError, UnicodeError, InvalidSignature, x509.ExtensionNotFound):
            raise KeyUnavailable from None

    def context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.check_hostname = False  # Private CA plus explicit SPKI, not DNS trust.
        try:
            context.load_verify_locations(cadata=self.read("ca.crt").decode("ascii"))
            base = "/proc/self/fd" if Path("/proc/self/fd").is_dir() else "/dev/fd"
            with self.descriptor("core.key") as key, self.descriptor("client.crt") as cert:
                context.load_cert_chain(f"{base}/{cert}", f"{base}/{key}")
            return context
        except (ValueError, UnicodeError, ssl.SSLError, OSError):
            raise KeyUnavailable from None

    def hashes(self):
        return {name: hashlib.sha256(self.read(name)).hexdigest() for name in ("core.key", "ca.crt", "client.crt")}

    def remove_owned(self, expected):
        if set(expected) != {"core.key", "ca.crt", "client.crt"} or set(p.name for p in self.root.iterdir()) != set(expected):
            raise KeyUnavailable
        actual = self.hashes()
        if any(not hmac.compare_digest(actual[name], expected[name]) for name in actual):
            raise KeyUnavailable
        identities = {name: (self.root / name).lstat() for name in actual}
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for name, previous in identities.items():
                current = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if (current.st_ino, current.st_mtime_ns, current.st_size, current.st_nlink) != (previous.st_ino, previous.st_mtime_ns, previous.st_size, 1):
                    raise KeyUnavailable
                os.unlink(name, dir_fd=directory)
            os.fsync(directory)
        finally:
            os.close(directory)
        self.root.rmdir()
