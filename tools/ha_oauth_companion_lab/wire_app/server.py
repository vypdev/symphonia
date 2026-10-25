"""Hidden disposable Supervisor App: CSR wire and native reset admission only.

No provider or production API. Internal TLS and verified Ingress are separate;
all material is synthetic and the fixture stops after its original 20 minutes.
"""
from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import sqlite3
import ssl
import threading
import time
from types import SimpleNamespace

from tools.ha_oauth_companion_lab.app.server import BoundedTLSHTTPServer
from tools.ha_oauth_companion_lab.enrollment_probe import Issuer, crypto, fingerprint
from tools.ha_oauth_companion_lab.key_custody_probe import Locked, PrivateFiles, encoded
from tools.ha_oauth_companion_lab.native_reset_probe import IngressStubConsumer, pack
from tools.ha_oauth_companion_lab.recovery_probe import RecoveryVault


ROOT=Path("/data/wire-lab")
MARKER="symphonia-live-wire-lab-v1"
ORIGIN="http://127.0.0.1"  # Exact internal test origin; no browser/HTTPS claim.


def unique_json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:
                raise Locked("duplicate_field")
            result[key]=value
        return result
    value=json.loads(raw,object_pairs_hook=pairs)
    if not isinstance(value,dict):
        raise Locked("object_required")
    return value


def cookie(raw,name):
    found=[]
    if not isinstance(raw,str) or len(raw)>4096:
        raise Locked("cookie_refused")
    for part in raw.split(";"):
        key,separator,value=part.strip().partition("=")
        if separator and key==name:
            found.append(value)
    if len(found)!=1 or re.fullmatch(r"[A-Za-z0-9_-]{40,128}",found[0]) is None:
        raise Locked("cookie_refused")
    return found[0]


class State:
    def __init__(self):
        fresh=not ROOT.exists()
        if fresh:
            ROOT.mkdir(mode=0o700)
            with PrivateFiles(ROOT) as files:
                files.publish("owned.json",encoded({"marker":MARKER,"installation":secrets.token_hex(16),
                    "expires":int(time.time())+1200}),exclusive=True)
                files.publish("fault.json",encoded({"once":True}),exclusive=True)
            RecoveryVault.create(ROOT/"grants")
            issuer=Issuer.create(ROOT/"issuer");issuer.close()
        with PrivateFiles(ROOT) as files:
            self.meta=unique_json(files.read("owned.json"))
        if self.meta.get("marker")!=MARKER or type(self.meta.get("expires")) is not int:
            raise Locked("unowned_wire_fixture")
        if not time.time()<self.meta["expires"]<=time.time()+1200:
            raise Locked("wire_fixture_expired")
        self.vault=RecoveryVault(ROOT/"grants")
        try:
            self.issuer=Issuer(ROOT/"issuer")
        except Locked:
            self.issuer=None  # Missing private TLS/CA key never reprovisions.
        self.challenge=self.issuer.challenge() if fresh else None
        self.sessions={}

    def public_signer(self):
        x509,*_=crypto()
        with PrivateFiles(ROOT/"issuer") as files:
            files.read("state.sqlite",1048576)
        db=sqlite3.connect(f"file:{ROOT/'issuer/state.sqlite'}?mode=ro",uri=True)
        try:
            epoch,serial,peer=db.execute("SELECT epoch,serial,peer FROM pair").fetchone()
            if epoch!=0 or serial is None:
                return None
            matches=[]
            for (pem,) in db.execute("SELECT certificate FROM issuance WHERE certificate IS NOT NULL"):
                if not isinstance(pem,str) or len(pem)>8192:
                    raise Locked("invalid_public_pair_record")
                cert=x509.load_pem_x509_certificate(pem.encode())
                if str(cert.serial_number)==serial and fingerprint(cert.public_key())==peer:
                    if cert.not_valid_after_utc.timestamp()<=time.time():
                        raise Locked("pair_certificate_expired")
                    matches.append(cert.public_key())
            if len(matches)!=1:
                raise Locked("public_pair_unavailable")
            return SimpleNamespace(public=matches[0],installation=self.meta["installation"])
        finally:
            db.close()

    def session(self,identity,browser=None,*,create=False):
        now=time.time()
        self.sessions={key:value for key,value in self.sessions.items() if now<value[1].request["expires"]}
        existing=self.sessions.get(browser)
        if existing and existing[0]==identity and not existing[1].used:
            return existing[1]
        if not create or len(self.sessions)>=8:
            raise Locked("private_browser_context_required")
        signer=self.public_signer()
        if signer is None:
            raise Locked("pair_required")
        consumer=IngressStubConsumer(self.vault,signer,identity[0],expected_origin=ORIGIN)
        self.sessions[consumer.browser]=(identity,consumer)
        return consumer

    def fault(self,point):
        if point!="reset_key_staged":
            return
        with PrivateFiles(ROOT) as files:
            data=unique_json(files.read("fault.json"))
            if data=={"once":True}:
                files.publish("fault.json",encoded({"once":False}))
                raise OSError("synthetic_key_publication_failure")

    def revoke_public_pair(self):
        db=sqlite3.connect(ROOT/"issuer/state.sqlite")
        try:
            db.execute("UPDATE pair SET epoch=epoch+1,serial=NULL,peer=NULL")
            db.execute("DELETE FROM challenge")
            db.commit()
        finally:
            db.close()


class CommonHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass
    def send(self,status,value,*,cookie_header=None):
        raw=encoded(value)
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Cache-Control","no-store")
        self.send_header("Connection","close")
        if cookie_header:
            self.send_header("Set-Cookie",cookie_header)
        try:
            self.end_headers();self.wfile.write(raw)
        except OSError:
            pass
        self.close_connection=True
    def data(self):
        lengths=self.headers.get_all("Content-Length",[])
        if (len(lengths)!=1 or not lengths[0].isdigit() or not 0<int(lengths[0])<=16384
                or self.headers.get("Transfer-Encoding") or self.headers.get("Content-Type")!="application/json"):
            raise Locked("body_refused")
        raw=self.rfile.read(int(lengths[0]))
        if len(raw)!=int(lengths[0]):
            raise Locked("body_refused")
        self.server.parsing_complete(self.connection)
        return unique_json(raw)


class TLSHandler(CommonHandler):
    def do_GET(self):
        self.server.parsing_complete(self.connection);self.send(404,{"accepted":False})
    def do_POST(self):
        if self.path!="/internal/ha-oauth/v1":
            self.send(404,{"accepted":False});return
        try:
            data=self.data();issuer=self.server.state.issuer
            if type(data.get("version")) is not int or data["version"]!=1 or data.get("profile")!="oauth":
                raise Locked("profile_refused")
            op=data.get("op")
            if op=="pair.enroll" and set(data)=={"op","version","profile","challenge","csr"}:
                receipt,cert=issuer.enroll(data["challenge"],data["csr"])
                self.send(200,{"receipt":receipt,"certificate":cert});return
            peer=self.connection.getpeercert(binary_form=True)
            if not issuer.accepts(peer,data.get("epoch")):
                raise Locked("peer_refused")
            if op=="hello" and set(data)=={"op","version","profile","epoch"}:
                self.send(200,{"accepted":True});return
            if op=="pair.renew" and set(data)=={"op","version","profile","epoch","csr","proof"}:
                receipt,cert=issuer.renew(peer,data["epoch"],data["csr"],proof=data["proof"])
                self.send(200,{"receipt":receipt,"certificate":cert});return
            raise Locked("operation_refused")
        except (Locked,ValueError,UnicodeError,TypeError):
            self.send(403,{"accepted":False,"reason":"wire_request_refused"})


class IngressHandler(CommonHandler):
    def identity(self):
        if self.client_address[0]!="172.30.32.2":
            raise Locked("trusted_ingress_peer_required")
        users=self.headers.get_all("X-Remote-User-Id",[])
        paths=self.headers.get_all("X-Ingress-Path",[])
        cookies=self.headers.get_all("Cookie",[])
        if (len(users)!=1 or re.fullmatch(r"[a-f0-9]{32}",users[0]) is None or len(paths)!=1
                or re.fullmatch(r"/api/hassio_ingress/[A-Za-z0-9_-]+",paths[0]) is None or len(cookies)!=1):
            raise Locked("trusted_ingress_context_required")
        session=cookie(cookies[0],"ingress_session")
        if re.fullmatch(r"[a-f0-9]{128}",session) is None:
            raise Locked("ingress_session_required")
        return users[0],hashlib.sha256(session.encode()).hexdigest(),paths[0]

    def do_GET(self):
        self.server.parsing_complete(self.connection)
        if self.path!="/":
            self.send(404,{"accepted":False});return
        try:
            identity=self.identity();state=self.server.state
            value={"installation":state.meta["installation"],"phase":state.vault.phase(),
                "tls_available":state.issuer is not None,"expires":state.meta["expires"]}
            try:
                state.vault.read_all();value["credentials_locked"]=False
            except Locked:
                value["credentials_locked"]=True
            signer=state.public_signer()
            if signer is None:
                x509,*_=crypto()
                value.update(challenge=state.challenge,
                    server_pin=fingerprint(x509.load_pem_x509_certificate((ROOT/"issuer/server.crt").read_bytes()).public_key()),
                    ca_certificate=(ROOT/"issuer/ca.crt").read_text())
                self.send(200,value);return
            try:
                browser=cookie(self.headers.get("Cookie",""),"symphonia_probe")
            except Locked:
                browser=None
            consumer=state.session(identity,browser,create=True)
            value.update(request=pack(consumer.request),csrf=consumer.csrf)
            self.send(200,value,cookie_header=f"symphonia_probe={consumer.browser}; Path={identity[2]}; Secure; HttpOnly; SameSite=Strict")
        except (Locked,ValueError,TypeError):
            self.send(403,{"accepted":False,"reason":"private_context_refused"})

    def do_POST(self):
        if self.path!="/reset":
            self.send(404,{"accepted":False});return
        try:
            identity=self.identity()
            browser=cookie(self.headers.get("Cookie",""),"symphonia_probe")
            consumer=self.server.state.session(identity,browser)
            data=self.data();origins=self.headers.get_all("Origin",[])
            if set(data)!={"approval","csrf"} or len(origins)!=1:
                raise Locked("reset_request_refused")
            consumer.submit(data["approval"],actor=identity[0],browser=browser,csrf=data["csrf"],origin=origins[0],
                test_checkpoint=self.server.state.fault)
            self.server.state.revoke_public_pair()
            self.send(200,{"accepted":True,"phase":self.server.state.vault.phase(),"pair_revoked":True,
                "history_retained":self.server.state.vault.db.execute("SELECT value FROM history").fetchone()[0]=="retained-synthetic-history"})
        except OSError:
            self.send(503,{"accepted":False,"phase":self.server.state.vault.phase(),"reason":"key_publication_failed"})
        except (Locked,ValueError,UnicodeError,TypeError):
            self.send(403,{"accepted":False,"reason":"reset_authority_refused"})


class IngressServer(HTTPServer):
    def get_request(self):
        raw,address=self.socket.accept();raw.settimeout(2)
        def expire():
            try:
                raw.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        timer=threading.Timer(2,expire);timer.daemon=True
        self.parsing=(raw,timer);timer.start()
        return raw,address
    def parsing_complete(self,connection):
        if getattr(self,"parsing",None) and self.parsing[0] is connection:
            _,timer=self.parsing;self.parsing=None;timer.cancel();timer.join(timeout=1)
    def shutdown_request(self,request):
        self.parsing_complete(request);super().shutdown_request(request)
    def handle_error(self,request,address):
        pass  # Safe receipt carries failure; never echo HTTP input/URLs.


def main():
    if os.geteuid()==0:
        os.chown("/data",10001,10001);os.setgroups([]);os.setgid(10001);os.setuid(10001)
    os.environ.clear();os.umask(0o077)
    state=State();stop=threading.Event();tls=None;worker=None
    ingress=IngressServer(("0.0.0.0",8099),IngressHandler);ingress.state=state;ingress.timeout=0.5
    try:
        if state.issuer is not None:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_3
            context.load_cert_chain(str(ROOT/"issuer/server.crt"),str(ROOT/"issuer/server.key"))
            context.load_verify_locations(str(ROOT/"issuer/ca.crt"));context.verify_mode=ssl.CERT_OPTIONAL
            tls=BoundedTLSHTTPServer(("0.0.0.0",8098),context,None)
            tls.RequestHandlerClass=TLSHandler;tls.state=state
            worker=threading.Thread(target=tls.serve_forever,daemon=True);worker.start()
        for sig in (signal.SIGINT,signal.SIGTERM):
            signal.signal(sig,lambda *args:stop.set())
        print(json.dumps({"lab":"wire_ready","uid":os.geteuid(),"tls_available":tls is not None}),flush=True)
        while not stop.is_set() and time.time()<state.meta["expires"]:
            ingress.handle_request()
    finally:
        ingress.server_close()
        if tls:
            tls.shutdown();tls.server_close();worker.join(timeout=3)
        state.vault.close()
        if state.issuer:
            state.issuer.close()


if __name__=="__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"lab":"wire_stopped","error_type":type(error).__name__}),flush=True)
        raise SystemExit(1) from None
