# Disposable HA OAuth companion experiments

Research only. These fixtures do not implement a Spotify connection, production
companion, provider token store or full v1 protocol. Run only in the guarded
`symphonia-ha-lab` environment described in [the lab guide](../../docs/development/ha-app-lab.md).
The [dated results](../../docs/development/ha-oauth-companion-lab-2026-10-25.md)
state precisely which parts passed and which remain blocked.

## Three independent experiments

1. `core_probe.py` boots a second **isolated** real Core instance with a fresh
   temporary config, synthetic owner/admins/non-admin, native HTTP config-flow
   endpoints and native callback. It uses no provider endpoint and forbids token
   exchange. It checks reconfigure/reauth, per-request actor, per-attempt PKCE,
   staged-only callback, logout/disable and saved-file canaries.
2. `transport_probe.py` creates a short-lived test CA/certificates/challenge and
   invokes the Supervisor-managed fixture App over internal DNS and strict TLS
   1.3. The CA/certificates are **pre-provisioned fixtures**: this is not proof
   of production CSR issuance, protected key storage or upgrade rotation.
3. `backup_probe.py` creates actual Supervisor partial backups of the fixture
   App and disposable Core, reads only selected canary members, tests protected
   archive decryption and AEAD records, then restores **only the fixture App**.
   It removes its exact Core control file and created backups in `finally`.
   It never restores Core or imports a production backup.

The transport App metadata is named `app-metadata.fixture.json` deliberately, so a
normal HA App repository scan cannot discover/install it. Supervisor 2026.10.4
recursively scans `config.*` with a supported extension; an extra word between
`config.` and `.json` would still match. The fixture filename avoids that
[discovery pattern](https://github.com/home-assistant/supervisor/blob/2026.10.4/supervisor/store/data.py#L157-L163).
Only lab staging
renames it to `config.yaml`. Its source has no host ports, mounts or Core/API
permissions. Its configured lifetime is 1,200 seconds. All key values are generated;
none are printed, committed or passed as CLI arguments.

## Reproduce the isolated native HTTP proof

Resume the existing guarded lab without rebuilding the main App:

```sh
PYTHONPATH=. python3 -c 'from tools.ha_app_lab import _start_container, _start_supervisor; _start_container(); _start_supervisor()'
docker exec symphonia-ha-lab docker inspect homeassistant --format '{{.Image}}'
```

Use the returned **exact image ID**, not a moving tag, for the following command.
The dated run used `sha256:dd1ad589936601cacb1b4797d17e27ce762b5147fb46b0e8e3d5486ab95e56c3`:

```sh
docker exec -i symphonia-ha-lab docker run --rm -i --network none --entrypoint python3 \
  --tmpfs /tmp:mode=1777 --tmpfs /config:mode=0700 \
  sha256:dd1ad589936601cacb1b4797d17e27ce762b5147fb46b0e8e3d5486ab95e56c3 - \
  < tools/ha_oauth_companion_lab/core_probe.py
```

No host/HA configuration volume, inherited Supervisor token or external network
is available in this invocation. The fixture also clears its environment before
bootstrapping. A preliminary direct `docker exec homeassistant` bootstrap is
not the accepted isolation recipe; use the separate networkless container.

The same HTTP/storage proof passed on official Core 2026.10.3 in the host Docker
Engine, independently of the stopped Supervisor lab:

```sh
docker pull ghcr.io/home-assistant/home-assistant@sha256:407b89cd11a8cb67d388d21739a226c74acbbebe1ac59e3b83b11b43ce76b98f
docker run --rm -i --network none --entrypoint python3 \
  --tmpfs /tmp:mode=1777 --tmpfs /config:mode=0700 \
  ghcr.io/home-assistant/home-assistant@sha256:407b89cd11a8cb67d388d21739a226c74acbbebe1ac59e3b83b11b43ce76b98f - \
  < tools/ha_oauth_companion_lab/core_probe.py
```

The pinned image is retained for reproduction. No container or personal config
persists after `--rm`. This additional image does not prove Supervisor topology
or real browser/provider behavior on 2026.10.3.

## Stage the private transport proof

These steps are a lab-operator recipe, not an installation script for an owner's
HA. Confirm the lab image/label guard before each session. Refuse unknown existing
paths; do not replace another App or modify existing HA credentials.

1. Create a new `/mnt/supervisor/apps/local/symphonia_oauth_lab_transport` inside
   the devcontainer. Copy the three `app/` fixture files, renaming only
   `app-metadata.fixture.json` to `config.yaml`. The App does not run from the checkout.
2. Run `ha store reload`, then `ha apps install local_symphonia_oauth_lab_transport`
   through `docker exec symphonia-ha-lab`. Installation builds the pinned Python
   base; no package manager or additional library is used in this App.
3. Generate the synthetic material from Core:

```sh
docker exec -i symphonia-ha-lab docker exec -i homeassistant python3 - prepare \
  < tools/ha_oauth_companion_lab/transport_probe.py
```

4. Copy only the newly generated `app-data/excluded` and `app-data/included`
   directories from `/tmp/symphonia-oauth-companion-lab-fixture-v3` in Core to
   the App's own `/mnt/supervisor/apps/data/local_symphonia_oauth_lab_transport`
   directory. A tar pipe between the two lab processes works on this nested
   Docker profile; Docker's archive endpoint did not see the runtime tmp mount.
   Never print those bytes. Refuse unowned existing fixture/data directories.
5. Start that App, then run:

```sh
docker exec -i symphonia-ha-lab docker exec -i homeassistant python3 - probe \
  < tools/ha_oauth_companion_lab/transport_probe.py
docker exec -i symphonia-ha-lab docker exec -i homeassistant python3 - stalls \
  < tools/ha_oauth_companion_lab/transport_probe.py
docker exec -i symphonia-ha-lab docker exec -i homeassistant python3 - \
  < tools/ha_oauth_companion_lab/backup_probe.py
```

The App consumes its on-disk enrollment challenge at startup; a restart needs a
new explicit fixture. Backup restore intentionally removes excluded keys and
leaves it locked/stopped. The backup experiment uses synthetic plaintext controls
to demonstrate a **negative baseline**, not an acceptable key-storage policy.
The AEAD wrapping key stays outside the copied record; its production source is
not selected by this test.

## Cleanup and evidence

Check that the fixture reports `locked_after_restore_or_unprovisioned`, that no
probe backups remain and that `.storage/symphonia_oauth_lab_backup_control` is
absent. Supervisor uses `DELETE /backups/{slug}` for removing only the backups
created by the run. Do not delete backups by broad name/path patterns.

Uninstall only `local_symphonia_oauth_lab_transport`. Remove its three staged
sources only after byte comparisons with the checkout; retain unexpected edits.
Remove generated PKI directories only when their `.owned` marker is exactly
`symphonia-synthetic-oauth-lab-v1`. Stop the guarded lab with
`python3 tools/ha_app_lab.py stop`; retain its pre-existing named volumes.

Ordinary CI runs eighteen fixture-policy tests without Core, Docker or external
network. Eight use loopback sockets: two real TLS handshake cases and six HTTP
identity-stub cases for idle/trickled headers/body, early certificate rejection
and a truncated enrollment followed by valid retry. Accepted connections have
both an idle timeout and a fixed two-second TLS/HTTP parsing window. The
watchdog covers wrapping/handshake and is cancelled before pairing policy runs.
The actual `stalls` command additionally keeps a trickling peer active while a
healthy Core client waits. This is not concurrency, rate or general denial-of-
service certification.

```sh
PYTHONPATH=src:. python3 -m unittest tests.test_ha_oauth_companion_lab -v
```

Receipts contain only modes, versions, status codes and booleans. Archive bytes,
client/server keys, HA access tokens, pairing challenges and raw callback URLs
must not enter evidence. These tests do not fulfill the 80-case production
budget or the 16-case live-provider/browser matrix.
