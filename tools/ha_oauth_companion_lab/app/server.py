"""Disposable TLS fixture; externally provisioned synthetic certs, no provider IO."""
from __future__ import annotations

import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import signal
import ssl
import threading
import time


class Pairing:
    def __init__(self, challenge, *, clock=time.monotonic):
        self.challenge, self.clock = challenge, clock
        self.deadline = clock() + 300
        self.peer = None
        self.epoch = 0

    def request(self, value, peer):
        if not isinstance(value, dict) or set(value) - {"op", "challenge", "version", "profile", "epoch"}:
            return 400
        if type(value.get("version")) is not int or value.get("version") != 1 or value.get("profile") != "oauth":
            return 403
        if not peer:
            return 403
        op = value.get("op")
        if op == "pair.enroll":
            supplied = value.get("challenge")
            if not self.challenge or self.clock() >= self.deadline or not isinstance(supplied, str):
                return 403
            if not hmac.compare_digest(supplied, self.challenge):
                return 403
            self.challenge = None
            self.peer = peer
            return 200
        if type(value.get("epoch")) is not int or peer != self.peer or value.get("epoch") != self.epoch:
            return 403
        if op == "hello":
            return 200
        if op == "pair.revoke":
            self.epoch += 1
            self.peer = None
            return 200
        return 403


class BoundedTLSHTTPServer(HTTPServer):
    """Bound idle handshakes/reads before the synchronous handler can block."""

    def __init__(self, address, context, pairing, *, connection_timeout=2.0):
        super().__init__(address, Handler)
        self.tls_context = context
        self.pairing = pairing
        self.connection_timeout = connection_timeout

    def get_request(self):
        raw, address = self.socket.accept()
        raw.settimeout(self.connection_timeout)
        try:
            return self.tls_context.wrap_socket(raw, server_side=True), address
        except BaseException:
            raw.close()
            raise


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status):
        body = json.dumps({"lab_only": True, "accepted": status == 200}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        self.respond(404)

    def do_POST(self):
        if self.path != "/internal/ha-oauth/v1":
            self.respond(404)
            return
        cert = self.connection.getpeercert(binary_form=True)
        if not cert:
            self.respond(403)
            return
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= 16384:
            self.respond(400)
            return
        if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Type") != "application/json":
            self.respond(400)
            return
        try:
            data = json.loads(self.rfile.read(int(lengths[0])))
        except (ValueError, UnicodeError):
            self.respond(400)
            return
        peer = hashlib.sha256(cert).digest()
        self.respond(self.server.pairing.request(data, peer))


def main():
    base = Path("/data/excluded")
    if not all((base / name).is_file() for name in ("server.key", "server.crt", "ca.crt", "enrollment.json")):
        print('{"lab":"locked_after_restore_or_unprovisioned"}', flush=True)
        return 0
    settings = json.loads((base / "enrollment.json").read_text())
    # A process restart must not re-arm a consumed enrollment challenge.
    (base / "enrollment.json").unlink()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(str(base / "server.crt"), str(base / "server.key"))
    context.load_verify_locations(str(base / "ca.crt"))
    context.verify_mode = ssl.CERT_OPTIONAL
    os.environ.clear()
    if os.getuid() == 0:
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    server = BoundedTLSHTTPServer(("0.0.0.0", 8098), context, Pairing(settings["challenge"]))
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *args: stop.set())
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    print('{"lab":"private_transport_ready","limit_seconds":1200}', flush=True)
    stop.wait(1200)
    server.shutdown()
    server.server_close()
    print('{"lab":"stopped"}', flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
