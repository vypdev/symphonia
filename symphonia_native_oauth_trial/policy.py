"""Pure, fixed policy for the finite native OAuth validation trial."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import math
import json
import re
import stat

REDIRECT = "https://my.home-assistant.io/redirect/oauth"
SCOPE = "user-read-private"
PROFILE = "trial_read_private"
LIFETIME = 1200
BOOTSTRAP_LIFETIME = 300
PORT = 8098
MAX_BODY = 16384
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_SLUG = re.compile(r"(?:local|[a-f0-9]{8})_symphonia_native_oauth_trial\Z")
_OPS = {
    "hello": frozenset(),
    "pair.enroll": frozenset({"challenge", "csr", "actor"}),
    "status": frozenset({"pair_id"}),
    "attempt.start": frozenset({"binding", "verifier"}),
    "attempt.stage": frozenset({"binding", "code"}),
    "attempt.cancel": frozenset({"binding", "reason"}),
    "attempt.complete": frozenset({"binding"}),
    "grant.refresh": frozenset({"binding", "confirmation_flow"}),
    "pair.revoke": frozenset({"pair_id"}),
}


class TrialError(Exception):
    """Only a closed category crosses an adapter boundary."""

    CATEGORIES = frozenset({
        "invalid_request", "invalid_client", "invalid_target", "invalid_binding",
        "expired", "clock_invalid", "bootstrap_unavailable", "locked",
        "wrong_actor", "conflict", "denied", "uncertain", "invalid_grant",
        "unavailable", "unsupported_account", "invalid_scope", "tls_identity",
    })

    def __init__(self, reason: str):
        self.reason = reason if reason in self.CATEGORIES else "unavailable"
        super().__init__(self.reason)


def identifier(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise TrialError("invalid_request")
    return value


def client_id(value: object) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 256
            or not value.strip() or any(not 32 <= ord(c) <= 126 for c in value)):
        raise TrialError("invalid_client")
    return value


def app_alias(value: object) -> str:
    if not isinstance(value, str) or _SLUG.fullmatch(value) is None:
        raise TrialError("invalid_target")
    return value.replace("_", "-")


def profile(redirect: object, scope: object) -> None:
    if redirect != REDIRECT or scope != SCOPE:
        raise TrialError("invalid_binding")


def integer(value: object, *, maximum: int = 2**53 - 1) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise TrialError("invalid_request")
    return value


def lifetime(started: object, deadline: object, last_seen: object, now: object) -> int:
    start, end, seen = integer(started), integer(deadline), integer(last_seen)
    if type(now) not in (int, float) or not math.isfinite(now):
        raise TrialError("clock_invalid")
    if end - start != LIFETIME or not start <= seen <= end or now < seen:
        raise TrialError("clock_invalid")
    if now >= end:
        raise TrialError("expired")
    return end


def bootstrap(issued: object, deadline: object, consumed: object, now: object) -> None:
    start, end = integer(issued), integer(deadline)
    if (type(consumed) is not bool or consumed or end - start != BOOTSTRAP_LIFETIME
            or type(now) not in (int, float) or not math.isfinite(now)
            or not start <= now < end):
        raise TrialError("bootstrap_unavailable")


def private_file(*, mode: int, owner: int, expected_owner: int, links: int,
                 size: int, maximum: int = 16384) -> None:
    if (not stat.S_ISREG(mode) or stat.S_IMODE(mode) != 0o600 or owner != expected_owner
            or links != 1 or not 0 < size <= maximum):
        raise TrialError("locked")


@dataclass(frozen=True)
class Binding:
    installation: str
    pair_id: str
    actor: str
    flow: str
    attempt: str
    pair_epoch: int
    credential_epoch: int
    provider: str
    client_id: str
    profile: str
    redirect: str
    deadline: int

    @classmethod
    def parse(cls, value: object) -> Binding:
        if not isinstance(value, dict) or set(value) != {f.name for f in fields(cls)}:
            raise TrialError("invalid_binding")
        for key in ("installation", "pair_id", "actor", "flow", "attempt"):
            identifier(value[key])
        for key in ("pair_epoch", "credential_epoch", "deadline"):
            integer(value[key])
        client_id(value["client_id"])
        if (value["provider"] != "spotify" or value["profile"] != PROFILE
                or value["redirect"] != REDIRECT):
            raise TrialError("invalid_binding")
        return cls(**value)

    def wire(self) -> dict:
        return asdict(self)

    def require(self, other: Binding, now: float) -> None:
        if self != other:
            raise TrialError("invalid_binding")
        if type(now) not in (int, float) or not 0 <= now <= 2**53 - 1 or not math.isfinite(now):
            raise TrialError("clock_invalid")
        if now >= self.deadline:
            raise TrialError("expired")


def envelope(value: object) -> dict:
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
        raise TrialError("invalid_request")
    op = value.get("op")
    if not isinstance(op, str) or op not in _OPS or set(value) != {"version", "op"} | _OPS[op]:
        raise TrialError("invalid_request")
    if "binding" in value:
        Binding.parse(value["binding"])
    if "reason" in value and value["reason"] not in ("denied", "cancelled"):
        raise TrialError("invalid_request")
    for name in ("actor", "pair_id", "confirmation_flow"):
        if name in value:
            identifier(value[name])
    for name, maximum in (("challenge", 256), ("csr", 8192), ("code", 2048)):
        if name in value and (not isinstance(value[name], str) or not 1 <= len(value[name]) <= maximum):
            raise TrialError("invalid_request")
    if "verifier" in value and (not isinstance(value["verifier"], str)
                               or re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", value["verifier"]) is None):
        raise TrialError("invalid_request")
    return value


def strict_json(raw: bytes, maximum: int):
    def pairs(items):
        document = {}
        for key, value in items:
            if key in document:
                raise ValueError
            document[key] = value
        return document
    def reject_constant(value):
        raise ValueError
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= maximum:
        raise TrialError("invalid_request")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=reject_constant)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise TrialError("invalid_request") from None
