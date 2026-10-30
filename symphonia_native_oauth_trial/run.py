"""Manual finite service; no environment/provider override or restart provisioning."""
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import signal
import stat
import time

from aiohttp import web

from .application import Trial
from .keys import PrivateFiles, Vault
from .policy import TrialError, lifetime, strict_json
from .provider import FixedHTTP, Spotify
from .server import Server
from .store import Store
from .tls import Authority, provision

ROOT = Path("/data/native_trial")


def initialize(root, clock):
    started, installation = int(clock()), secrets.token_hex(16)
    with PrivateFiles(root) as files:
        files.create("provisioning.marker", installation.encode())
    keys = root / "oauth_keys"
    keys.mkdir(mode=0o700)
    provision(keys, installation, started, started + 1200)
    with PrivateFiles(keys) as files:
        files.create("bootstrap.challenge", secrets.token_urlsafe(32).encode())
        wrapping_id = hashlib.sha256(files.read("wrapping.key", 32)).hexdigest()
    store = Store.provision(root / "trial.sqlite", installation, started)
    store.close()
    authority = Authority(keys, installation, started + 1200)
    identity = {"schema": 1, "installation": installation, "started": started,
                "deadline": started + 1200, "server_pin": authority.pin, "wrapping_id": wrapping_id}
    with PrivateFiles(root) as files:
        files.create("identity.json", json.dumps(identity, separators=(",", ":")).encode())


def compose(root, provider, *, fresh=False, clock=time.time):
    """Test composition may inject ports; shipping main always selects Spotify."""
    if fresh:
        if list(root.iterdir()):
            raise TrialError("locked")
        initialize(root, clock)
    with PrivateFiles(root) as files:
        identity = strict_json(files.read("identity.json", 4096), 4096)
        if files.read("provisioning.marker", 32).decode("ascii") != identity.get("installation"):
            raise TrialError("locked")
    store = Store(root / "trial.sqlite")
    try:
        meta = store.meta()
        if (set(identity) != {"schema", "installation", "started", "deadline", "server_pin", "wrapping_id"}
                or type(identity["schema"]) is not int or identity["schema"] != 1
                or any(identity[name] != meta[name] for name in ("installation", "started", "deadline"))):
            raise TrialError("locked")
        lifetime(meta["started"], meta["deadline"], meta["last_seen"], clock())
        if meta["retired"]:
            raise TrialError("expired")
        keys = root / "oauth_keys"
        authority = Authority(keys, meta["installation"], meta["deadline"])
        if authority.pin != identity["server_pin"]:
            raise TrialError("locked")
        vault = Vault(keys, identity["wrapping_id"])
        vault._cipher()  # Check existing wrapping identity even before the first grant.
        with PrivateFiles(keys) as files:
            challenge = None if meta["bootstrap_used"] else files.read("bootstrap.challenge", 43).decode("ascii")
        if challenge is not None and len(challenge) != 43:
            raise TrialError("locked")
        trial = Trial(store, provider, vault, clock, authority=authority, challenge=challenge)
        return Server(trial, store, authority, challenge, clock)
    except BaseException:
        store.close()
        raise


def prepare_service_identity():
    """Only a new fixed data directory is owned; never recursively chown data."""
    fresh = False
    if os.getuid() == 0:
        try:
            ROOT.mkdir(mode=0o700)
            os.chown(ROOT, 10001, 10001)
            fresh = True
        except FileExistsError:
            info = ROOT.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 10001 or stat.S_IMODE(info.st_mode) != 0o700:
                raise TrialError("locked")
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    elif os.getuid() != 10001:
        raise TrialError("locked")
    os.umask(0o077)
    return fresh


async def serve(server, stop, *, host="0.0.0.0", ingress_port=8099):
    private = await asyncio.start_server(server.private_stream, host, 8098,
        ssl=server.authority.context(), ssl_handshake_timeout=3, ssl_shutdown_timeout=0.5,
        limit=16384, backlog=16)
    runner = web.AppRunner(server.ingress_app(), access_log=None, shutdown_timeout=3)
    await runner.setup()
    try:
        await web.TCPSite(runner, host, ingress_port, backlog=16).start()
        remaining = max(0, server.state.meta()["deadline"] - server.clock())
        # Monotonic timeout cannot be extended by a wall-clock change in this process.
        try:
            async with asyncio.timeout(remaining):
                while not stop.is_set():
                    phase = server.state.status(server.clock())["phase"]
                    if phase in {"expired", "locked"}:
                        break
                    try:
                        await asyncio.wait_for(stop.wait(), 1)
                    except TimeoutError:
                        pass
        except TimeoutError:
            pass
    finally:
        private.close()
        await private.wait_closed()
        await server.close_connections()
        await runner.cleanup()
        server.trial.transient.clear()
        server.state.close()


async def main(fresh):
    server = compose(ROOT, Spotify(FixedHTTP()), fresh=fresh)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    print('{"phase":"trial_ready","lifetime_seconds":1200}', flush=True)
    await serve(server, stop)
    print('{"phase":"trial_stopped"}', flush=True)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.CRITICAL)
    try:
        fresh = prepare_service_identity()
        os.environ.clear()
        asyncio.run(main(fresh))
    except TrialError as error:
        print(json.dumps({"phase": "locked" if error.reason != "expired" else "expired"}), flush=True)
        raise SystemExit(0 if error.reason == "expired" else 78) from None
    except Exception:
        print('{"phase":"unavailable"}', flush=True)
        raise SystemExit(78) from None
