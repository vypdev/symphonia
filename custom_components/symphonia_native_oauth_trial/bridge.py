"""Fixed private channel and public-authorizer adaptation; no HA credential reads."""
import asyncio
import base64
import hashlib
import hmac
import json
import math
import re
import socket
import ssl
import time
from urllib.parse import parse_qs, urlsplit

import aiohttp
from cryptography import x509

from .keys import CoreKeys, KeyUnavailable, spki

REDIRECT = "https://my.home-assistant.io/redirect/oauth"
SCOPE = "user-read-private"
SLUG = re.compile(r"(?:local|[0-9a-f]{8})_symphonia_native_oauth_trial\Z")


class BridgeError(Exception):
    def __init__(self, reason="unavailable"):
        self.reason = reason if reason in {"invalid_input", "tls_identity", "expired", "unavailable", "rejected"} else "rejected"
        super().__init__(self.reason)


def document(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError
            value[key] = item
        return value
    def reject_constant(value):
        raise ValueError
    try:
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= 16384:
            raise ValueError
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=reject_constant)
        if not isinstance(result, dict):
            raise ValueError
        pending = [(result, 1)]
        while pending:
            value, depth = pending.pop()
            if depth > 32:
                raise ValueError
            items = value.values() if isinstance(value, dict) else value
            for item in items:
                if isinstance(item, float) and not math.isfinite(item):
                    raise ValueError
                if isinstance(item, (dict, list)):
                    pending.append((item, depth + 1))
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise BridgeError("invalid_input") from None


def bootstrap(raw):
    try:
        value = document(raw.encode("utf-8"))
        if set(value) != {"installation", "pin", "challenge", "deadline", "profile"}:
            raise ValueError
        if (re.fullmatch(r"[a-f0-9]{32}", value["installation"]) is None
                or re.fullmatch(r"[a-f0-9]{64}", value["pin"]) is None
                or re.fullmatch(r"[A-Za-z0-9_-]{43}", value["challenge"]) is None
                or value["profile"] != "trial_read_private" or type(value["deadline"]) is not int
                or not time.time() < value["deadline"] <= time.time() + 1200):
            raise ValueError
        return value
    except (ValueError, TypeError, AttributeError):
        raise BridgeError("invalid_input") from None


async def authorize(hass, flow_id, client_id, factory):
    """Factory must construct a NEW public Core PKCE implementation each time."""
    impl = factory(hass, "symphonia_native_oauth_trial", client_id=client_id,
                   authorize_url="https://accounts.spotify.com/authorize",
                   token_url="https://accounts.spotify.com/api/token", client_secret="")
    try:
        if impl.redirect_uri != REDIRECT:
            raise BridgeError("invalid_input")
        verifier = impl.code_verifier
        if not isinstance(verifier, str) or re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier) is None:
            raise BridgeError("invalid_input")
        url = await impl.async_generate_authorize_url(flow_id)
        # Scope is explicit, added without disturbing Core's signed state.
        from yarl import URL
        url = str(URL(url).update_query(scope=SCOPE))
        query = parse_qs(urlsplit(url).query)
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        if (urlsplit(url).scheme != "https" or urlsplit(url).netloc != "accounts.spotify.com"
                or urlsplit(url).path != "/authorize" or query.get("client_id") != [client_id]
                or query.get("redirect_uri") != [REDIRECT] or query.get("scope") != [SCOPE]
                or query.get("code_challenge_method") != ["S256"] or query.get("code_challenge") != [expected]
                or query.get("response_type") != ["code"] or len(query.get("state", [])) != 1):
            raise BridgeError("invalid_input")
        return url, verifier
    finally:
        impl.code_verifier = ""


def callback_input(request, flow_id, value):
    if (request is None or request.path != "/auth/external/callback" or request.method != "GET"
            or not isinstance(value, dict) or not isinstance(value.get("state"), dict)
            or set(value["state"]) != {"flow_id", "redirect_uri"}
            or value["state"] != {"flow_id": flow_id, "redirect_uri": REDIRECT}):
        raise BridgeError("invalid_input")
    kind = "code" if set(value) == {"state", "code"} else "error" if set(value) == {"state", "error"} else None
    if kind is None or set(request.query) != {"state", kind} or any(len(request.query.getall(name)) != 1 for name in request.query):
        raise BridgeError("invalid_input")
    raw = value[kind]
    if (not isinstance(raw, str) or not 1 <= len(raw) <= (2048 if kind == "code" else 256)
            or any(not 33 <= ord(c) <= 126 for c in raw) or request.query[kind] != raw
            or not 1 <= len(request.query["state"]) <= 4096):
        raise BridgeError("invalid_input")
    return ("stage", raw) if kind == "code" else ("cancel", "denied")



class Bridge:
    def __init__(self, slug, pin, deadline, keys: CoreKeys):
        if (not isinstance(slug, str) or SLUG.fullmatch(slug) is None or not isinstance(pin, str)
                or re.fullmatch(r"[a-f0-9]{64}", pin) is None or type(deadline) is not int or not 0 < deadline < 2**53):
            raise BridgeError("invalid_input")
        self.alias, self.pin, self.deadline, self.keys = slug.replace("_", "-"), pin, deadline, keys
        self.server_der = None

    async def call(self, value, *, paired=True):
        remaining = min(5, self.deadline - time.time())
        if remaining <= 0:
            raise BridgeError("expired")
        raw = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode()
        if len(raw) > 16384:
            raise BridgeError("invalid_input")
        resolver, writer, connection = aiohttp.AsyncResolver(), None, None
        try:
            context = await asyncio.to_thread(self.keys.context) if paired else ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if not paired:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            context.minimum_version = ssl.TLSVersion.TLSv1_3
            async with asyncio.timeout(remaining):
                addresses = await resolver.resolve(self.alias, 8098, family=socket.AF_INET)
                if not addresses:
                    raise BridgeError("unavailable")
                connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                connection.setblocking(False)
                await asyncio.get_running_loop().sock_connect(connection, (addresses[0]["host"], 8098))
                reader, writer = await asyncio.open_connection(sock=connection, ssl=context,
                    server_hostname=self.alias, ssl_handshake_timeout=remaining, ssl_shutdown_timeout=0.5, limit=16384)
                cert = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
                if not cert or not hmac.compare_digest(spki(x509.load_der_x509_certificate(cert).public_key()), self.pin):
                    raise BridgeError("tls_identity")
                self.server_der = cert
                # No bootstrap, verifier, code or confirmation bytes precede the pin.
                path = "/internal/ha-oauth/v1" if paired else "/internal/ha-oauth/v1/enroll"
                writer.write((f"POST {path} HTTP/1.1\r\nHost: {self.alias}\r\n"
                              f"Content-Type: application/json\r\nContent-Length: {len(raw)}\r\nConnection: close\r\n\r\n").encode() + raw)
                await writer.drain()
                head = await reader.readuntil(b"\r\n\r\n")
                lines = head.decode("ascii").split("\r\n")
                status = lines[0].split(" ")
                if len(status) < 2 or status[0] != "HTTP/1.1" or status[1] != "200":
                    raise BridgeError("rejected")
                headers = {}
                for line in lines[1:-2]:
                    name, sep, content = line.partition(":")
                    if not sep or name.lower() in headers:
                        raise BridgeError("rejected")
                    headers[name.lower()] = content.strip()
                length = headers.get("content-length", "")
                if (not length.isascii() or not length.isdigit() or not 0 < int(length) <= 16384
                        or "transfer-encoding" in headers or not headers.get("content-type", "").startswith("application/json")):
                    raise BridgeError("rejected")
                response = document(await reader.readexactly(int(length)))
                if type(response.get("version")) is not int or response["version"] != 1 or response.get("ok") is not True or set(response) != {"version", "ok", "result"} or not isinstance(response["result"], dict):
                    raise BridgeError("rejected")
                return response["result"]
        except (OSError, ValueError, KeyUnavailable, asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
            raise BridgeError("unavailable") from None
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except (OSError, TimeoutError):
                    pass
            elif connection is not None:
                connection.close()
            await resolver.close()


_REQUEST_MARKER = "symphonia_native_oauth_trial_consumed_actions"


def validated_actor(request, user_key):
    user = request.get(user_key) if request is not None else None
    return user.id if user and user.is_active and user.is_admin else None


def mark_request(request, flow_id):
    if request is not None:
        consumed = request.setdefault(_REQUEST_MARKER, set())
        if not isinstance(consumed, set) or len(consumed) >= 32:
            raise BridgeError("rejected")
        consumed.add(flow_id)


async def native_action(request, actor, expected_actor, flow_id, value):
    if (request is None or actor is None or actor != expected_actor or request.method != "POST"
            or request.path != "/api/config/config_entries/flow/" + flow_id
            or flow_id in request.get(_REQUEST_MARKER, set())):
        raise BridgeError("rejected")
    actual = await request.json()
    if (not isinstance(actual, dict) or actual != value
            or any(type(actual.get(key)) is not type(item) for key, item in value.items())):
        raise BridgeError("rejected")
    mark_request(request, flow_id)
    return actor


def validate_reference(value):
    required = {"schema", "installation", "pair_id", "pair_epoch", "credential_epoch", "actor", "deadline", "app_slug", "client_id", "pin", "material_hashes"}
    try:
        if not isinstance(value, dict):
            value = dict(value)
        if not required <= set(value) or set(value) - required - {"binding", "retired", "key_cleanup_pending"} or type(value["schema"]) is not int or value["schema"] != 1:
            raise ValueError
        for name in ("installation", "pair_id"):
            if not isinstance(value[name], str) or re.fullmatch(r"[a-f0-9]{32}", value[name]) is None:
                raise ValueError
        if not isinstance(value["actor"], str) or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value["actor"]) is None:
            raise ValueError
        for name in ("deadline", "pair_epoch", "credential_epoch"):
            if type(value[name]) is not int or not 0 <= value[name] < 2**53:
                raise ValueError
        if (not isinstance(value["client_id"], str) or not 1 <= len(value["client_id"]) <= 256
                or not value["client_id"].strip() or any(not 32 <= ord(c) <= 126 for c in value["client_id"])):
            raise ValueError
        Bridge(value["app_slug"], value["pin"], value["deadline"], None)
        hashes = value["material_hashes"]
        if not isinstance(hashes, dict) or set(hashes) != {"core.key", "ca.crt", "client.crt"} or any(not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None for digest in hashes.values()):
            raise ValueError
        for name in ("retired", "key_cleanup_pending"):
            if name in value and type(value[name]) is not bool:
                raise ValueError
        if "binding" in value:
            binding = value["binding"]
            names = {"installation", "pair_id", "pair_epoch", "credential_epoch", "actor", "client_id", "deadline"}
            if (not isinstance(binding, dict) or set(binding) != names | {"provider", "profile", "redirect", "flow", "attempt"}
                    or any(binding[name] != value[name] or type(binding[name]) is not type(value[name]) for name in names)
                    or binding["provider"] != "spotify" or binding["profile"] != "trial_read_private" or binding["redirect"] != REDIRECT
                    or any(not isinstance(binding[name], str) or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", binding[name]) is None for name in ("flow", "attempt"))):
                raise ValueError
        return value
    except (ValueError, TypeError, KeyError):
        raise BridgeError("invalid_input") from None
