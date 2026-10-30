"""Exact Spotify HTTPS adapter; test ports are injected only by composition."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import hashlib
import time

import aiohttp

from .application import Grant
from .policy import Binding, SCOPE, TrialError, integer, strict_json

TOKEN = "https://accounts.spotify.com/api/token"
ME = "https://api.spotify.com/v1/me"
BODY_LIMIT = 65536
REQUEST_SECONDS = 10


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes = field(repr=False)


class FixedHTTP:
    async def request(self, method, url, *, deadline, data=None, headers=None):
        if (method, url) not in {("POST", TOKEN), ("GET", ME)}:
            raise TrialError("invalid_target")
        remaining = min(REQUEST_SECONDS, deadline - time.time())
        if remaining <= 0:
            raise TrialError("expired")
        resolver = aiohttp.AsyncResolver()
        try:
            # AsyncResolver owns cancellable c-ares work, not a detached DNS thread.
            async with asyncio.timeout(remaining):
                connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False, limit=1)
                async with aiohttp.ClientSession(connector=connector, trust_env=False,
                        auto_decompress=False, timeout=aiohttp.ClientTimeout(total=remaining)) as session:
                    async with session.request(method, url, data=data,
                                               headers={**(headers or {}), "Accept-Encoding": "identity"},
                                               allow_redirects=False) as response:
                        if response.status in range(300, 400) or response.headers.get("Content-Encoding", "identity") != "identity":
                            raise TrialError("uncertain")
                        chunks, size = [], 0
                        while chunk := await response.content.read(min(8192, BODY_LIMIT + 1 - size)):
                            chunks.append(chunk)
                            size += len(chunk)
                            if size > BODY_LIMIT:
                                raise TrialError("uncertain")
                        return Response(response.status, b"".join(chunks))
        except (aiohttp.ClientError, OSError, TimeoutError):
            raise TrialError("uncertain") from None
        finally:
            await resolver.close()


def credential(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 4096 or any(not 33 <= ord(c) <= 126 for c in value):
        raise TrialError("uncertain")
    return value


class Spotify:
    def __init__(self, transport, clock=time.time):
        self.transport, self.clock = transport, clock

    @staticmethod
    def _document(response: Response):
        try:
            document = strict_json(response.body, BODY_LIMIT)
        except TrialError:
            raise TrialError("uncertain") from None
        if response.status != 200:
            if response.status in (400, 401) and document.get("error") == "invalid_grant":
                raise TrialError("invalid_grant")
            raise TrialError("uncertain")
        return document

    def _grant(self, document, *, prior=None):
        scope = document.get("scope", SCOPE if prior is not None else None)
        if not isinstance(scope, str) or scope.split() != [SCOPE]:
            raise TrialError("invalid_scope")
        kind = document.get("token_type")
        if not isinstance(kind, str) or kind.lower() != "bearer":
            raise TrialError("uncertain")
        try:
            expires = integer(document.get("expires_in"), maximum=86400)
        except TrialError:
            raise TrialError("uncertain") from None
        if expires == 0:
            raise TrialError("uncertain")
        access = credential(document.get("access_token"))
        refresh = credential(document.get("refresh_token", prior.refresh if prior else None))
        return Grant(access, refresh, int(self.clock()) + expires)

    async def exchange(self, binding: Binding, code: str, verifier: str) -> Grant:
        response = await self.transport.request("POST", TOKEN, deadline=binding.deadline,
            data={"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
                  "client_id": binding.client_id, "redirect_uri": binding.redirect})
        return self._grant(self._document(response))

    async def refresh(self, binding: Binding, grant: Grant) -> Grant:
        response = await self.transport.request("POST", TOKEN, deadline=binding.deadline,
            data={"grant_type": "refresh_token", "refresh_token": grant.refresh,
                  "client_id": binding.client_id})
        return self._grant(self._document(response), prior=grant)

    async def account(self, binding: Binding, grant: Grant) -> str:
        response = await self.transport.request("GET", ME, deadline=binding.deadline,
                                                headers={"Authorization": "Bearer " + grant.access})
        document = self._document(response)
        account = document.get("account_id")
        if not isinstance(account, str) or not 1 <= len(account) <= 256 or any(not 33 <= ord(c) <= 126 for c in account):
            raise TrialError("unsupported_account")
        return hashlib.sha256(binding.installation.encode() + b"\0" + account.encode()).hexdigest()
