"""Use cases depend only on pure policy and semantic ports."""
from __future__ import annotations

from dataclasses import dataclass, field
import hmac
from typing import Protocol

from .policy import Binding, TrialError


@dataclass(frozen=True)
class Grant:
    access: str = field(repr=False)
    refresh: str = field(repr=False)
    expires: int


class Provider(Protocol):
    async def exchange(self, binding: Binding, code: str, verifier: str) -> Grant: ...
    async def refresh(self, binding: Binding, grant: Grant) -> Grant: ...
    async def account(self, binding: Binding, grant: Grant) -> str: ...


class Cipher(Protocol):
    def seal(self, binding: Binding, grant: Grant) -> bytes: ...
    def open(self, binding: Binding, sealed: bytes) -> Grant: ...


class State(Protocol):
    def enroll(self, actor, peer, now): ...
    def start(self, binding, now): ...
    def stage(self, binding, now): ...
    def validate_staged(self, binding, now): ...
    def claim(self, binding, now, *, refresh_flow=None): ...
    def commit(self, binding, owner, sealed, account, now, *, refreshed=False): ...
    def assert_owner(self, binding, owner, now): ...
    def finish_error(self, owner, *, uncertain): ...
    def grant(self, binding, now): ...
    def terminal(self, binding, now, phase): ...
    def retire(self): ...
    def status(self, now): ...


class Trial:
    def __init__(self, state: State, provider: Provider, cipher: Cipher, clock, *, authority=None, challenge=None):
        self.state, self.provider, self.cipher, self.clock = state, provider, cipher, clock
        self.authority, self.challenge = authority, challenge
        self.transient: dict[str, tuple[str, str | None]] = {}

    def enroll(self, actor, csr, challenge):
        if not self.challenge or not hmac.compare_digest(challenge, self.challenge):
            raise TrialError("bootstrap_unavailable")
        peer = self.authority.validate_request(csr, actor)
        meta = self.state.enroll(actor, peer, self.clock())
        self.challenge = None
        result = {name: meta[name] for name in ("installation", "pair_id", "pair_epoch", "credential_epoch", "actor", "deadline")}
        result.update(self.authority.issue_request(csr, actor, meta["pair_id"], meta["started"]))
        return result

    def start(self, binding: Binding, verifier: str):
        self.state.start(binding, self.clock())
        self.transient[binding.attempt] = (verifier, None)
        return self.state.status(self.clock())

    def stage(self, binding: Binding, code: str):
        value = self.transient.get(binding.attempt)
        if value is None:
            raise TrialError("conflict")
        verifier, previous = value
        if previous is not None:
            if not hmac.compare_digest(previous, code):
                raise TrialError("conflict")
            # Validate even a duplicate against the immutable original binding.
            self.state.validate_staged(binding, self.clock())
            return self.state.status(self.clock())
        self.state.stage(binding, self.clock())
        self.transient[binding.attempt] = (verifier, code)
        return self.state.status(self.clock())

    def terminal(self, binding: Binding, phase: str):
        self.state.terminal(binding, self.clock(), phase)
        self.transient.pop(binding.attempt, None)
        return self.state.status(self.clock())

    async def complete(self, binding: Binding):
        owner = self.state.claim(binding, self.clock())
        if owner is None:
            return self.state.status(self.clock())
        value = self.transient.pop(binding.attempt, None)
        try:
            if value is None or value[1] is None:
                raise TrialError("uncertain")
            verifier, code = value
            try:
                grant = await self.provider.exchange(binding, code, verifier)
            finally:
                value = code = verifier = None
            self.state.assert_owner(binding, owner, self.clock())
            account = await self.provider.account(binding, grant)
            sealed = self.cipher.seal(binding, grant)
            self.state.commit(binding, owner, sealed, account, self.clock())
        except BaseException as error:
            self.state.finish_error(owner, uncertain=not isinstance(error, TrialError) or error.reason not in {"invalid_grant", "invalid_scope", "unsupported_account"})
            raise
        return self.state.status(self.clock())

    async def refresh(self, binding: Binding, confirmation_flow: str):
        owner = self.state.claim(binding, self.clock(), refresh_flow=confirmation_flow)
        if owner is None:
            return self.state.status(self.clock())
        try:
            sealed, original_account = self.state.grant(binding, self.clock())
            grant = self.cipher.open(binding, sealed)
            replacement = await self.provider.refresh(binding, grant)
            self.state.assert_owner(binding, owner, self.clock())
            account = await self.provider.account(binding, replacement)
            if not hmac.compare_digest(original_account, account):
                raise TrialError("unsupported_account")
            sealed = self.cipher.seal(binding, replacement)
            self.state.commit(binding, owner, sealed, account, self.clock(), refreshed=True)
        except BaseException as error:
            self.state.finish_error(owner, uncertain=not isinstance(error, TrialError) or error.reason not in {"invalid_grant", "invalid_scope", "unsupported_account"})
            raise
        return self.state.status(self.clock())

    def retire(self):
        self.state.retire()
        self.transient.clear()
