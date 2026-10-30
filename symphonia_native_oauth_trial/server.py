"""Read-only Ingress and independently authenticated finite OAuth listener."""
import hmac
import asyncio
import html
import ipaddress
import json
import re

from aiohttp import web
from cryptography import x509

from .policy import Binding, MAX_BODY, TrialError, envelope, strict_json
from .tls import spki


def ingress_allowed(peer, headers):
    try:
        address = ipaddress.ip_address(peer)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return (str(address) == "172.30.32.2"
                and re.fullmatch(r"/api/hassio_ingress/[A-Za-z0-9_-]{16,256}", headers.get("X-Ingress-Path", "")) is not None
                and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", headers.get("X-Remote-User-Id", "")) is not None
                and "system-admin" in headers.get("X-Remote-User-Groups", "").split(","))
    except ValueError:
        return False


class Server:
    def __init__(self, trial, state, authority, challenge, clock):
        self.trial, self.state, self.authority = trial, state, authority
        self.clock = clock
        self.tasks = set()

    @property
    def challenge(self):
        return self.trial.challenge

    def ingress_app(self):
        app = web.Application(client_max_size=MAX_BODY)
        app.router.add_get("/health", self.health)
        app.router.add_get("/", self.page)
        return app

    async def health(self, request):
        return web.json_response({"trial": True}, headers={"Cache-Control": "no-store"})

    async def page(self, request):
        if not ingress_allowed(request.remote, request.headers):
            raise web.HTTPForbidden
        status = self.state.status(self.clock())
        phase = status["phase"]
        deadline = status.get("deadline")
        if type(deadline) is not int or not 0 < deadline < 2**53:
            phase, deadline = "locked", 0
        allowed = {"unpaired", "paired", "pending", "staged", "exchanging", "active", "refreshing", "verified", "uncertain", "locked", "expired", "retired", "cancelled", "denied", "failed"}
        if phase not in allowed:
            phase = "locked"
        spanish = request.headers.get("Accept-Language", "")[:128].lower().startswith("es")
        title = "Prueba OAuth de Symphonia" if spanish else "Symphonia OAuth trial"
        actions = {
            "unpaired": "Copia el bloque en la integración nativa de Home Assistant." if spanish else "Copy the block into the native Home Assistant integration.",
            "paired": "Abre la integración de prueba en Home Assistant, luego Reconfigurar → Conectar Spotify." if spanish else "Open the trial integration in Home Assistant, then Reconfigure → Connect Spotify.",
            "pending": "Completa el consentimiento de Spotify; aún no hay grant activo." if spanish else "Finish Spotify consent; no grant is active yet.",
            "staged": "Confirma de nuevo en el formulario nativo; el código aún no se ha intercambiado." if spanish else "Confirm again in the native form; the code has not been exchanged.",
            "active": "Reinicia solo la App y confirma una renovación en el formulario nativo." if spanish else "Restart only the App, then confirm one refresh in the native form.",
            "verified": "OAuth y renovación verificados. Retira la prueba y revoca el acceso dedicado en Spotify." if spanish else "OAuth and refresh verified. Retire the trial and revoke dedicated Spotify access.",
        }
        action = actions.get(phase, "Consulta el formulario nativo y la guía de retirada; no repitas operaciones inciertas." if spanish else "Use the native form and retirement guide; do not repeat uncertain operations.")
        block = ""
        meta = self.state.meta()
        if phase == "unpaired" and not meta["bootstrap_used"] and self.clock() < meta["started"] + 300 and self.challenge:
            bundle = {"installation": meta["installation"], "pin": self.authority.pin,
                      "challenge": self.challenge, "deadline": meta["deadline"], "profile": "trial_read_private"}
            heading = "Emparejamiento · 5 minutos" if spanish else "Bootstrap · 5 minutes"
            block = "<h2>" + heading + "</h2><pre tabindex='0'>" + html.escape(json.dumps(bundle, indent=2)) + "</pre>"
        labels = ("Límite UTC (epoch)", "Observado", "PKCE público · user-read-private · 20 minutos. Las claves de la App se excluyen de backups; la identidad de Core requiere backups de HA cifrados.") if spanish else ("Deadline (UTC epoch)", "Observed", "Public PKCE · user-read-private · 20 minutes. App keys are excluded from backups; Core pairing identity requires encrypted HA backups.")
        body = ("<!doctype html><html lang='" + ("es" if spanish else "en") + "'><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'><title>" + title + "</title>"
                "<style>body{font:1rem system-ui;margin:1.5rem;max-width:48rem;color:CanvasText;background:Canvas}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:LinkText}</style>"
                "<main><h1>" + title + "</h1><p role='status'>" + html.escape(phase) + "</p><p>" + action + "</p>"
                "<p>" + labels[0] + ": " + str(deadline) + " · " + labels[1] + ": " + str(int(self.clock())) + "</p>" + block +
                "<p>" + labels[2] + "</p>"
                "<p><a href='./'>Actualizar / Refresh</a></p></main></html>")
        return web.Response(text=body, content_type="text/html", headers={"Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'"})

    async def private_stream(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        status = 200
        try:
            # TLS handshake is separately bounded by asyncio.start_server.
            async with asyncio.timeout(3):
                head = await reader.readuntil(b"\r\n\r\n")
                if len(head) > 8192:
                    raise TrialError("invalid_request")
                lines = head.decode("ascii").split("\r\n")
                target = lines[0].split(" ")
                if len(target) != 3 or target[0] != "POST" or target[2] != "HTTP/1.1" or target[1] not in {"/internal/ha-oauth/v1", "/internal/ha-oauth/v1/enroll"}:
                    raise TrialError("invalid_request")
                headers = {}
                for line in lines[1:-2]:
                    name, separator, value = line.partition(":")
                    if not separator or name.lower() in headers:
                        raise TrialError("invalid_request")
                    headers[name.lower()] = value.strip()
                length = headers.get("content-length", "")
                if (not length.isascii() or not length.isdigit() or len(length) > 5
                        or not 0 < int(length) <= MAX_BODY or "transfer-encoding" in headers
                        or headers.get("content-type") != "application/json"):
                    raise TrialError("invalid_request")
                connection = writer.get_extra_info("ssl_object")
                peer = connection.getpeercert(binary_form=True) if connection else None
                enrolling = target[1].endswith("/enroll")
                meta = self.state.meta()
                if not enrolling and (not peer or not meta["peer"] or not hmac.compare_digest(spki(x509.load_der_x509_certificate(peer).public_key()), meta["peer"])):
                    status = 403
                    raise TrialError("tls_identity")  # No unauthenticated RPC body read.
                value = envelope(strict_json(await reader.readexactly(int(length)), MAX_BODY))
            result = await self.process(value, enrolling=enrolling)
            response = {"version": 1, "ok": True, "result": result}
        except asyncio.CancelledError:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, TimeoutError):
                pass
            self.tasks.discard(task)
            raise
        except TrialError as error:
            response = {"version": 1, "ok": False, "reason": error.reason}
        except Exception:
            response = {"version": 1, "ok": False, "reason": "unavailable"}
        try:
            body = json.dumps(response, separators=(",", ":")).encode()
            writer.write((f"HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n").encode() + body)
            await writer.drain()
        except (OSError, TimeoutError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, TimeoutError):
                pass
            self.tasks.discard(task)

    async def close_connections(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def process(self, value, *, enrolling):
        meta = self.state.meta()
        if enrolling:
            if value["op"] != "pair.enroll":
                raise TrialError("bootstrap_unavailable")
            return self.trial.enroll(value["actor"], value["csr"], value["challenge"])
        if value["op"] == "pair.enroll":
            raise TrialError("invalid_request")
        return await self.dispatch(value, meta)

    async def dispatch(self, value, meta):
        op = value["op"]
        if op == "hello":
            return {"installation": meta["installation"], "deadline": meta["deadline"]}
        if op in ("status", "pair.revoke"):
            if value["pair_id"] != meta["pair_id"]:
                raise TrialError("invalid_binding")
            if op == "pair.revoke":
                self.trial.retire()
            return self.state.status(self.clock())
        binding = Binding.parse(value["binding"])
        if op == "attempt.start":
            return self.trial.start(binding, value["verifier"])
        if op == "attempt.stage":
            return self.trial.stage(binding, value["code"])
        if op == "attempt.cancel":
            return self.trial.terminal(binding, value["reason"])
        if op == "attempt.complete":
            return await self.trial.complete(binding)
        if op == "grant.refresh":
            return await self.trial.refresh(binding, value["confirmation_flow"])
        raise TrialError("invalid_request")
