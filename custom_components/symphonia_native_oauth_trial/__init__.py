"""Reference-only native OAuth trial entry; no entities, services or token sessions."""

DOMAIN = "symphonia_native_oauth_trial"


def record_runtime_cache():
    """Record only caches produced inside the fresh manifest-owned install."""
    import hashlib
    import importlib.util
    import os
    from pathlib import Path
    import stat
    root = Path(__file__).parent
    marker = root / ".source-owned.sha256"
    if not marker.is_file() or marker.is_symlink():
        return
    info = marker.stat()
    if info.st_uid != os.getuid() or info.st_nlink != 1 or not 1 <= info.st_size <= 4096:
        return
    raw = marker.read_bytes()
    if not raw.startswith(b"# SYMPHONIA_NATIVE_OAUTH_TRIAL_SOURCE_V1\n"):
        return
    output = root / ".cache-owned.sha256"
    if output.exists() or output.is_symlink():
        return
    lines = ["# SYMPHONIA_NATIVE_OAUTH_TRIAL_CACHE_V1 " + hashlib.sha256(raw).hexdigest()]
    for name in ("__init__", "config_flow", "bridge", "keys"):
        cache = Path(importlib.util.cache_from_source(str(root / (name + ".py"))))
        if cache.parent != root / "__pycache__" or not cache.exists():
            continue
        info = cache.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_size > 262144:
            return
        lines.append(hashlib.sha256(cache.read_bytes()).hexdigest() + "  " + cache.relative_to(root).as_posix())
    try:
        fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
        try:
            raw = ("\n".join(lines) + "\n").encode()
            while raw:
                size = os.write(fd, raw)
                if size <= 0:
                    raise OSError
                raw = raw[size:]
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        return


async def async_setup_entry(hass, entry):
    from .bridge import Bridge, BridgeError, validate_reference
    from .keys import CoreKeys, KeyUnavailable
    from pathlib import Path
    from homeassistant.exceptions import ConfigEntryError
    try:
        validate_reference(entry.data)
        if entry.data.get("retired") is True:
            hass.data.setdefault(DOMAIN, {})
            return True
        keys = CoreKeys(Path(hass.config.path(".storage", DOMAIN, entry.data["installation"])))
        if await hass.async_add_executor_job(keys.hashes) != dict(entry.data["material_hashes"]):
            raise KeyUnavailable
        Bridge(entry.data["app_slug"], entry.data["pin"], entry.data["deadline"],
               CoreKeys(Path(hass.config.path(".storage", DOMAIN, entry.data["installation"]))))
        await hass.async_add_executor_job(CoreKeys(Path(hass.config.path(".storage", DOMAIN, entry.data["installation"]))).context)
    except (BridgeError, KeyUnavailable, ValueError, TypeError):
        raise ConfigEntryError("trial_pair_key_unavailable") from None
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_unload_entry(hass, entry):
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


async def async_remove_entry(hass, entry):
    if entry.data.get("retired") is True and entry.data.get("key_cleanup_pending") is False:
        return
    from .bridge import Bridge, BridgeError, validate_reference
    from .keys import CoreKeys, KeyUnavailable
    from homeassistant.components import http
    from homeassistant.components.http import KEY_HASS_USER
    from pathlib import Path
    import logging
    import time
    request = http.current_request.get()
    user = request.get(KEY_HASS_USER) if request is not None else None
    if (not user or not user.is_active or not user.is_admin or request.method != "DELETE"
            or request.path != "/api/config/config_entries/entry/" + entry.entry_id):
        logging.getLogger(__name__).warning("trial_retirement_pending_stop_and_remove_trial_app")
        return
    try:
        value = validate_reference(entry.data)
        keys = CoreKeys(Path(hass.config.path(".storage", DOMAIN, value["installation"])))
        if value["deadline"] > time.time():
            bridge = Bridge(value["app_slug"], value["pin"], value["deadline"], keys)
            result = await bridge.call({"version": 1, "op": "pair.revoke", "pair_id": value["pair_id"]})
            if result.get("phase") not in ("expired", "retired"):
                raise BridgeError("rejected")
        await hass.async_add_executor_job(keys.remove_owned, value["material_hashes"])
    except (BridgeError, KeyUnavailable, OSError):
        logging.getLogger(__name__).warning("trial_retirement_pending_stop_and_remove_trial_app")
