"""Protected immutable files and AEAD adapter; never provisions on read failure."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import hashlib
import hmac
from contextlib import contextmanager

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .application import Grant
from .policy import Binding, TrialError, integer, private_file, strict_json


class PrivateFiles:
    def __init__(self, root: Path):
        self.fd = None
        try:
            self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(self.fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise TrialError("locked")
        except (OSError, TrialError):
            self.close()
            raise TrialError("locked") from None

    def __enter__(self):
        return self

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __exit__(self, *args):
        self.close()

    @staticmethod
    def name(value):
        if not isinstance(value, str) or re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", value) is None or ".." in value:
            raise TrialError("locked")
        return value

    def read(self, name: str, maximum=16384) -> bytes:
        fd = None
        try:
            fd = os.open(self.name(name), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
            info = os.fstat(fd)
            private_file(mode=info.st_mode, owner=info.st_uid, expected_owner=os.getuid(),
                         links=info.st_nlink, size=info.st_size, maximum=maximum)
            chunks, size = [], 0
            while size <= maximum:
                chunk = os.read(fd, maximum + 1 - size)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            after = os.fstat(fd)
            if size != info.st_size or size > maximum or (after.st_size, after.st_mtime_ns, after.st_nlink) != (info.st_size, info.st_mtime_ns, 1):
                raise TrialError("locked")
            return b"".join(chunks)
        except OSError:
            raise TrialError("locked") from None
        finally:
            if fd is not None:
                os.close(fd)

    def create(self, name: str, content: bytes):
        if not isinstance(content, bytes) or not 1 <= len(content) <= 16384:
            raise TrialError("locked")
        fd = None
        try:
            fd = os.open(self.name(name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
            pending = memoryview(content)
            while pending:
                count = os.write(fd, pending)
                if count <= 0:
                    raise OSError
                pending = pending[count:]
            os.fsync(fd)
            os.fsync(self.fd)
        except OSError:
            # A partial first provision remains visible and locks next startup.
            raise TrialError("locked") from None
        finally:
            if fd is not None:
                os.close(fd)

    @contextmanager
    def descriptor(self, name: str, maximum=16384):
        fd = None
        try:
            fd = os.open(self.name(name), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
            info = os.fstat(fd)
            private_file(mode=info.st_mode, owner=info.st_uid, expected_owner=os.getuid(),
                         links=info.st_nlink, size=info.st_size, maximum=maximum)
            yield fd
        except OSError:
            raise TrialError("locked") from None
        finally:
            if fd is not None:
                os.close(fd)


def aad(binding: Binding) -> bytes:
    return json.dumps(binding.wire(), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


class Vault:
    def __init__(self, root: Path, expected_key_id=None):
        self.root, self.expected_key_id = root, expected_key_id

    def _cipher(self):
        with PrivateFiles(self.root) as files:
            key = files.read("wrapping.key", 32)
        if len(key) != 32 or self.expected_key_id is not None and not hmac.compare_digest(hashlib.sha256(key).hexdigest(), self.expected_key_id):
            raise TrialError("locked")
        return AESGCM(key)

    def seal(self, binding: Binding, grant: Grant) -> bytes:
        raw = json.dumps({"access": grant.access, "refresh": grant.refresh, "expires": grant.expires},
                         sort_keys=True, separators=(",", ":")).encode()
        nonce = os.urandom(12)
        return nonce + self._cipher().encrypt(nonce, raw, aad(binding))

    def open(self, binding: Binding, sealed: bytes) -> Grant:
        try:
            if not isinstance(sealed, bytes) or not 29 <= len(sealed) <= 32768:
                raise TrialError("locked")
            raw = self._cipher().decrypt(sealed[:12], sealed[12:], aad(binding))
            document = strict_json(raw, 32740)
            if set(document) != {"access", "refresh", "expires"}:
                raise TrialError("locked")
            for name in ("access", "refresh"):
                value = document[name]
                if not isinstance(value, str) or not 1 <= len(value) <= 4096 or any(not 33 <= ord(c) <= 126 for c in value):
                    raise TrialError("locked")
            integer(document["expires"])
            return Grant(**document)
        except (InvalidTag, ValueError, TypeError, TrialError):
            raise TrialError("locked") from None
