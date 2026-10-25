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


## Install-local key and Core backup follow-up

The [separate dated report](../../docs/development/local-key-custody-lab-2026-10-25.md)
and [ADR 0008](../../docs/decisions/0008-install-local-oauth-keys-and-backups.md)
record the automatic-start decision. These scripts remain research tools, never
production imports or App package members. No recovery-kit feature is selected.

For `key_custody_probe.py`, use an **explicitly new**, labelled owned Docker
volume mounted at `/data`, the pinned Core 2026.10.3 image below, no network and
a read-only bind of the script at `/probe.py`. Refuse an existing volume; never
reuse an owner data volume. A creation wrapper may chown only the new `/data`
mount, drop all supplementary groups, then irreversibly set GID/UID 10001 before
running the fixture. This matches the campaign boundary; its root must be
`/data/vault`. The fixture needs the image's cryptography package, not a new
production dependency.

```sh
docker run --rm --network none --read-only \
  --mount type=volume,src=<new-owned-labelled-volume>,dst=/data \
  --mount type=bind,src=<absolute-research-script>,dst=/probe.py,readonly \
  --entrypoint python3 \
  ghcr.io/home-assistant/home-assistant@sha256:407b89cd11a8cb67d388d21739a226c74acbbebe1ac59e3b83b11b43ce76b98f \
  -c 'import os,runpy,sys; os.chown("/data",10001,10001); os.setgroups([]); os.setgid(10001); os.setuid(10001); sys.argv=["/probe.py","campaign"]; runpy.run_path("/probe.py",run_name="__main__")'
```

Run a second `--rm --network none --read-only --cap-drop ALL --user 10001:10001`
container against that same exact volume/script/image, with entrypoint `python3`
and arguments `/probe.py restart-check`. The expected receipt confirms the
existing key/grant without provisioning a new key. This is a container-replacement
proof, not a native Core restart/upgrade. After recording safe Boolean results,
verify the exact labels, `vault/owned.json` marker and absence of consumers before
removing only that volume. Do not print its key or grant files.

The independent `core_key_backup_probe.py` runs **only** through the guarded
`symphonia-ha-lab`; first resume it using the established guide and verify the
pinned image/label guards. It creates an exact owned synthetic Core namespace,
private pairing key and safe Store reference. It uses actual Supervisor partial
Core backups, reads only its two selected members, then deletes its backups and
files in `finally`. It never restores Core or uses provider credentials.

```sh
docker exec -i symphonia-ha-lab docker exec -i \
  -e SYMPHONIA_DISPOSABLE_HA_LAB=symphonia-ha-lab \
  homeassistant python3 - < tools/ha_oauth_companion_lab/core_key_backup_probe.py
```

The expected distinction is deliberate: an unprotected Core archive contains
the pairing identity; correct protected-archive decryption recovers it and a
wrong password fails. `core_key_excluded_from_backup` is **false**, while safe
Store/key permissions, new-process signature and cleanup flags are true. This
proves the selected HA trust profile, not Core exclusion or clone detection.
Independently verify zero backups with the exact campaign name prefix and the
absence of its two Core paths before stopping the guarded lab. If cleanup fails,
retain only the emitted owned backup slugs for exact recovery; do not broaden
cleanup to another App, backup or HA config path.


For the synthetic file/SQLite crash campaign, stage the complete `tools` package
anchor plus `key_custody_probe.py` and `key_publication_probe.py` read-only at
`/research`, with `PYTHONPATH=/research`. Use another explicitly new labelled
volume at `/data`, the same pinned Core image, no network, and UID 10001 after
preparing only that volume's owner. Run:

```text
python3 /research/tools/ha_oauth_companion_lab/key_publication_probe.py campaign
```

Eight child processes intentionally exit 83 at named publication/generation
boundaries; the parent reopens SQLite/files and checks old/new identity, history
and quiescent collection. A main exit 0 with all Boolean results true is the
accepted synthetic result. An unexpected child status fails the campaign.
It tests one record and no live collector or reset HTTP endpoint. Ordinary
`test_ha_oauth_key_publication_fixture.py` uses real SQLite/files and fake AEAD;
the pinned-container campaign provides the separate real-AEAD evidence. Inspect
the exact twelve owned case markers and volume labels/consumers before removing
that volume; never delete another application's data. The report records the
performed campaign and its remaining fault-plan gaps.

## Recovery and CSR successor

The [dated successor](../../docs/development/oauth-recovery-and-pairing-lab-2026-10-25.md)
documents `recovery_probe.py`, `enrollment_probe.py` and their exact limitations.
Stage both beside the regular `tools/__init__.py`, private-file/publication
fixtures and `app/server.py`, read-only at `/research`. Use the same pinned image,
fresh labelled volumes, no exterior network/host ports and UID/GID 10001 after
preparing only each fresh mount. The CSR campaign binds container loopback.

```text
python3 /research/tools/ha_oauth_companion_lab/enrollment_probe.py
python3 /research/tools/ha_oauth_companion_lab/recovery_probe.py
```

The CSR campaign has three deliberate child exits 83. The recovery campaign
has twenty-one, including seven reset/retirement fences and four inside-publication points,
plus four missing/wrong-key cases. Parent exit 0 and all Boolean
observations true are required. `test_ha_oauth_recovery_fixture.py` uses an
explicitly fake codec and test admission boolean; neither is native identity
or encryption proof. The scripts are not production endpoints or an installable
integration. The separate actual-wire experiment below now proves bounded
enrollment/renewal and native reset admission; final production/browser
conformance remains open.
Inspect exact volume labels, owned CSR/case markers, private file types/modes and
absence of consumers before removing only these synthetic volumes. Preserve
safe receipts/source hashes, never private material or challenges.

`native_reset_probe.py` is a third, independent native-HTTP experiment. Run it
in a fresh networkless pinned Core container, with read-only `/research`,
`PYTHONPATH=/research` and temporary `/tmp` and `/config` only. It bootstraps
its own Core and never mounts the owner's or guarded lab's existing config.
The actual Core actor/signature observations are separate from its explicit
Ingress/browser/Origin/CSRF stubs. No default production recovery permission
or native integration is installed by this script.


## Actual Supervisor CSR, renewal and native reset wire

`wire_lab_operator.py` stages the hidden `wire_app/` and temporary
`wire_core_fixture.py` component only in the exact pinned disposable lab. It
refuses another Core image/outer container. Follow the
[full recipe and teardown](../../docs/development/oauth-recovery-and-pairing-lab-2026-10-25.md#reproduction-and-cleanup),
using a fresh private receipts directory and always `cleanup` after
`receipt`. It preserves exact original Core configuration, creates/removes only
its synthetic users and owns its explicit App/component namespaces. No existing
user auth token is read. Core's internal Supervisor token stays in process.
The App has no host ports, broad mounts or API privileges; its fixed lifetime is
twenty minutes. The key-loss gate is bounded to 180 seconds after pairing.

Unlike the older isolated prototype, this experiment crosses actual Supervisor
Ingress and Core-to-App CSR/renewal TLS. Renewal independently requires a
current-key signature over the exact issued certificate, replacement CSR and
epoch. Public certificate bytes alone cannot renew. The final campaign passes
36 isolated CSR and 34 real-wire Boolean observations. Its manually supplied
cookies over HTTP are explicitly not Chrome/HTTPS or provider proof. Production
recovery authority/UX and final package rollout still need review.

`wire_reset_probe.py` adds one actual child death after credential reset commit
before issuer revocation. Stage it and `wire_app/server.py` with the complete
research package in the pinned networkless image and a fresh owned volume as
UID10001. Ten observations verify startup revokes before TLS, is idempotent,
preserves history and never rekeys. Its admission Boolean is a test stub.
Post-reset wire fixtures require explicit fresh provisioning; they never expose
a consumed challenge or silently re-arm enrollment after restart.

`wire_cancellation_probe.py` cancels the real asyncio task with explicitly fake
HA/auth APIs and a synthetic process-only Supervisor credential in the pinned
networkless image. Six observations distinguish interrupted/failed receipts
from success and verify scoped fake-user cleanup. No live Core config/user,
real credential, provider or native authorization is exercised.
