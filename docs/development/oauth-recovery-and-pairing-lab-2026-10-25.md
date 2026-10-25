# Native OAuth recovery and CSR pairing laboratory

**Date:** 2026-10-25. **Status:** bounded research for issue #30, not production
implementation or an owner-Home-Assistant pass. PR #29 is merged in develop at
`818a50e153ddee0b0569ed2bba6373c29b1bd2f3`; its approved head and merged tree
match. Its PR CI producer passed all seven jobs before merge.

## Environment and boundaries

The isolated CSR and recovery campaigns use the official Core 2026.10.3 image pinned to
`ghcr.io/home-assistant/home-assistant@sha256:407b89cd11a8cb67d388d21739a226c74acbbebe1ac59e3b83b11b43ce76b98f`,
Python 3.14.9 and cryptography 50.0.1. Each starts with a fresh labelled volume,
no exterior network, read-only source/image and service UID 10001. A small
wrapper prepares only that volume, clears supplementary groups and drops
GID/UID before executing research code. The CSR TLS listener binds container
loopback with no host mapping. No provider request, owner HA configuration,
Supervisor token, real credential or public callback is involved.

These fixtures use the image's existing crypto package; no production dependency
or final secret adapter is selected. Earlier native HTTP, Supervisor-internal
TLS and backup results remain separate evidence. Combining reports does not
turn a loopback CSR test into an end-to-end native enrollment pass.

## CSR issuance and persistent pairing

[The CSR fixture](../../tools/ha_oauth_companion_lab/enrollment_probe.py) generates
P-256 client keys/CSRs, validates signature/curve/hash/bounds, rejects caller
subjects/extensions and issues client certificates from a private local CA.
The public certificate is bound to the CSR key; no client private key is sent
to the issuer. The database holds public certificate/CSR metadata, serial,
key fingerprint, epoch and a hashed temporary challenge, not the CA key.

Thirty-six Boolean observations pass across these fourteen distinct scenario groups:

| Group | Observation |
| --- | --- |
| C01 | Issued public key matches the generated CSR key; identity is admitted |
| C02 | Wrong challenge cannot create an issuance |
| C03 | Challenge expiry rejects admission |
| C04 | Modified CSR signature is rejected |
| C05 | Unsupported curve is rejected |
| C06 | Caller-selected subject or authority extension is rejected |
| C07 | Oversized CSR is rejected |
| C08 | Consumed challenge replay and five failed attempts close that challenge |
| C09 | Wrong server SPKI pin stops before a request body reaches policy |
| C10 | A newly CSR-issued client certificate crosses real TLS; absent certificate is denied |
| C11 | Pair/CA reopen persists authority; missing existing CA key locks without provisioning |
| C12 | Current-key signature binds issued certificate, exact CSR and epoch; missing/attacker/malformed/substituted proof fails; renewal switches identity and rejects the old certificate; lost acknowledgement is stable |
| C13 | Revocation, changed epoch and OAuth/playback profile separation deny stale authority; explicit re-pair uses the new epoch |
| C14 | Three actual process deaths recover admitted/uncommitted/committed issuance correctly |

C14 deliberately exits child processes with `os._exit(83)` after challenge
consumption, before the certificate SQL commit and after commit/before an
acknowledgement. Reopen/status cannot mint a certificate. Pending issuance
cannot be replaced by a fresh challenge; explicit resume completes the admitted
request once, while a committed result remains stable. Public result retrieval
conveys no private-key possession. Pending-epoch revocation races remain part of
the full native lifecycle conformance gate.

Renewal requires an ECDSA signature made by the current paired private key over
a domain-separated document containing the exact issued certificate, epoch and
new CSR digests. Public certificate metadata, a substituted issuer signature or
a signature for another CSR/epoch cannot admit issuance. No private key crosses
the wire. The active epoch/serial fence makes a committed old proof stale; an
existing public receipt retrieves the committed result without another renewal.
This guard was added after review identified certificate-only internal
admission; mTLS remains independently required by the wire adapter. The
resulting certificate crosses TLS. The separate real-wire campaign below now exercises Core-to-App enrollment
and renewal over the Supervisor network. Concurrent deployment lifecycle, final
Core key-file adapter and package compatibility remain unproven. The fixture's
per-challenge counter is not a certified global per-minute rate limiter.

## Multi-record rotation and reset ordering

[The recovery fixture](../../tools/ha_oauth_companion_lab/recovery_probe.py)
uses three separately bound synthetic credential records and a complete active
reference set. A durable writer admission precedes file staging; an SQL switch
activates the entire set and key generation together. A live admitted owner
conservatively pins staged files. Collection holds the SQL admission fence and
does not use file age as evidence of terminal ownership.

Eighteen actual process deaths pass with real AES-GCM:

| Operation | Interruption points |
| --- | --- |
| Publish, 6 | Before a record, inside buffered private write, durable two-link publication, first staged record, before commit, after commit |
| Rotate, 8 | Inside buffered key write, durable two-link key publication, new key staged, first record staged, all records staged, before commit, after commit, obsolete records retired |
| Explicit reset, 4 | Durable reset fence, replacement key staged, before reset commit, after commit |

Reopen sees all old or all committed new records, never a mixed active set.
History survives. Reset remains `reset_pending` after an interrupted fence;
health/startup do not create a key or finish the reset. Explicit resume produces
an unpaired identity with no grant and requires new pairing/consent.

The reset caller is an explicitly named **test authorization stub**, not an
HTTP route or proof of a current HA administrator. No real API may turn a
submitted boolean into that authority. Native Ingress, Origin/CSRF, active-user
checks and unauthorized reset requests are proved separately below. The
file/SQL fixture alone cannot claim that authority or external provider revocation.

Twenty-three [ordinary tests](../../tests/test_ha_oauth_recovery_fixture.py) use
real files/SQLite and an explicitly fake codec. They cover owner/collector and
two-connection races, complete-set activation, partial writes, rollback,
epoch/reset fencing, corrupt/missing old/new keys or records, connection-bound
AAD, lost reset progress, health observation and preserved history. These are
policy evidence, not cryptography or native authorization evidence. Four
additional real-AEAD cases remove or substitute old/new keys: each locks without
creating a replacement. Quiescent collection removes only strictly named owned
partial publications after all writers exit; an active linked file or symlink
remains locked evidence. Process death inside a write is not a simulated power
loss or proof about every filesystem/hardware implementation.

## Fresh native administrator approval prototype

[The native reset prototype](../../tools/ha_oauth_companion_lab/native_reset_probe.py)
boots a separate Core 2026.10.3 with fresh temporary configuration, synthetic
users and real authenticated native config-flow HTTP endpoints. It imports no
owner configuration, Supervisor token or browser credential. Twenty-eight Boolean
observations pass: fresh same-admin begin/confirmation, non-admin/different-admin/
inactive-user/revoked-login denial, typed short-lived signed approval, changed
purpose/signature/expiry/replay denial, local reset once and preserved history.
A key-publication failure consumes its first approval and leaves reset pending.
A new native same-admin confirmation issues a distinct `resume` approval; it
finishes that durable intent without another epoch increment or replay. The
recovery was verified through the actual Core HTTP flow after the PR review
identified the missing resume path. No config entry or approval/private key is saved. Missing, malformed or substituted existing Core keys
block signing without replacement. Ingress actor/browser/Origin/CSRF inputs
are **explicit stubs**; their negative policy observations do not establish
real Supervisor or browser enforcement.

The inspected official Supervisor 2026.10.3
[Ingress API](https://github.com/home-assistant/supervisor/blob/2026.10.3/supervisor/api/ingress.py#L359-L395)
and [user cache](https://github.com/home-assistant/supervisor/blob/2026.10.3/supervisor/ingress.py#L37-L40)
show why a user header alone cannot be treated as a fresh active-admin proof.
The [key RFC](../architecture/local-key-custody-rfc.md#fresh-reset-authority-candidate--not-accepted-or-implemented)
therefore proposes a native signed recovery approval, final Ingress/CSRF
redemption, and no replacement network listener. This authority/disclosure/UX
extension is a **review candidate**, not an accepted production permission.
The explicit native setup view is the proposed approval-document surface;
no provider secret or long-term key is shown or included in a URL.

Thirteen additional [ordinary parsing/binding and resume cases](../../tests/test_ha_native_reset_fixture.py)
cover duplicate/oversized fields, current actor/install/profile, typed/bounded
epochs, exact purpose/identifier and expiry. Two regression cases use actual
SQL/files with fake AEAD/signature verification: failed reset needs a fresh
resume approval, while a competing completed resume fences a stale approval.
They do not substitute for cryptography or real native HTTP. The integrated suite passes **570 tests, no
skips**; combined application coverage remains 89%, with the unchanged 85% floor.
The final native source was repeated after its parser guards; all twenty-eight
observations pass. The container and all temporary users/config/key state are
removed with its temporary files and `--rm` lifecycle.

## Actual Core/Supervisor CSR and Ingress reset

The hidden [App fixture](../../tools/ha_oauth_companion_lab/wire_app/server.py),
[Core harness](../../tools/ha_oauth_companion_lab/wire_core_fixture.py), and
[guarded operator](../../tools/ha_oauth_companion_lab/wire_lab_operator.py) run
only in `symphonia-ha-lab`. The operator refuses an unknown/stopped outer lab or
an unexpected Core image. Its manifest/hash guards preserve the original Core
configuration and refuse cleanup after unrelated changes.

The executed environment is Core **2026.9.4**, Python **3.14.6**, cryptography
**48.0.1**, Supervisor **2026.10.4**, aarch64, Core digest
`ghcr.io/home-assistant/qemuarm-64-homeassistant@sha256:dd1ad589936601cacb1b4797d17e27ce762b5147fb46b0e8e3d5486ab95e56c3`.
This differs from the isolated Core 2026.10.3 campaign and owner platform.
The App drops to UID/GID 10001, has no host ports, mounts, Core or Supervisor
API privilege, and expires twenty minutes after explicit fresh provisioning.
A five-minute challenge is held only by its first process. Restart does not
extend either deadline or provision a replacement challenge/key.

Thirty-three Boolean observations pass through the actual wire:

- Core-generated CSR enrollment crosses private TLS after server-pin checking;
  wrong pin stops before the body. Wrong/consumed challenges, missing client
  identity, stale epoch, playback profile and unknown operations are denied.
- Renewal additionally verifies the current-key signature bound to the new CSR;
  a copied public certificate without mTLS and a wrong-key signature even within
  mTLS are denied. It activates the new Core key/certificate and rejects the previous
  certificate. Core cannot forge the Supervisor source peer, even with complete
  actor/path/session headers. TLS cannot reach the management reset route.
- Actual Ingress denies missing sessions and non-admin users. Three synthetic
  users are created and removed through Core APIs. No existing user/browser
  auth token is read; the Core internal Supervisor credential is used only in
  process to request synthetic user-bound Ingress sessions.
- After removing exactly the App CA, server and wrapping keys, Ingress remains
  live with locked credentials and no TLS. Startup creates none of those keys.
  Retained public pair metadata can still verify native approval.
- Real native HTTP rejects another administrator, a disabled administrator and
  a revoked login. **Ingress still returned HTTP 200 after deactivation** on
  this Supervisor version; headers/cache are not fresh authority. A new login
  of the same active actor is tested, not continuity of the original login.
- Wrong Origin and CSRF and forged approvals are denied by the App. A successful
  direct Supervisor backend GET plus the App-specific refusal body establishes
  that Origin denial is not merely a different proxy's rejection.
- An injected key-publication error consumes approval and leaves reset pending.
  Replay fails. A new native confirmation signs a fresh purpose-bound resume;
  final Ingress redemption completes once, revokes the pair and retains history.

A separate [reset-commit crash campaign](../../tools/ha_oauth_companion_lab/wire_reset_probe.py)
exits a real child process immediately after credential reset commit and before
issuer revocation. Nine Boolean observations pass on the pinned isolated
Core 2026.10.3 crypto image. Startup uses the durable `unpaired` phase as
revocation intent, clears the old pair/challenge idempotently **before** opening
TLS authority, preserves history and adds/replaces no private key. Pending or
completed reset phases also fence requests on any already-running TLS listener. A shared
lock serializes reset with renewal; TLS reads the phase through a separate
read-only SQLite connection and is tested from an actual worker thread.
Its reset admission is an explicit test stub; actual native admission is the
independent wire campaign above. This is one additional actual process death,
not one of the eighteen vault-publication deaths.

After reset, this disposable profile ends. Ingress states that fresh fixture
provisioning is required and returns no stale/null bootstrap challenge. Restart
cannot re-arm enrollment or mint replacement CA/server keys. The isolated CSR
campaign separately exercises explicit re-pair; post-reset production setup/UX
and key regeneration are outside this hidden wire fixture's scope.

The HTTP client manually sends a Secure cookie over lab HTTP. **This does not
prove Chrome cookie, iframe, SameSite, HTTPS or provider behavior.** Native
setup is an explicitly installed research component, not the final helper.
An initial App liveness-healthcheck omission and two harness programming errors
were corrected before the successful repeat; failed runs are not counted as
passes. The final operator/shim uses its own package namespace so it cannot
replace Core's existing modules. Thirteen ordinary boundary/target-guard/renewal tests are
separate from real-wire evidence.

The [cancellation regression](../../tools/ha_oauth_companion_lab/wire_cancellation_probe.py)
cancels the actual asyncio harness task after it records one fake user. Six
observations verify cancellation propagates, cleanup targets only that fake
user, and the receipt/phase say `CancelledError`/`failed` rather than success.
One ordinary regression also exercises this actual cancellation path with
explicitly fake dependencies; it restores the process environment/modules.
The pinned Core image supplies dependencies, but HA/auth APIs in this experiment
are explicit stubs; no additional native-authorization claim is made. The
harness sets success only after every observation/assertion completes, and an
incomplete non-Exception exit cannot produce a successful receipt. A retained
failed receipt prevents automatic retries; the operator must clean its owned
fixture before explicit fresh staging.

## Fault-plan progress and remaining gates

Every planned research ID has bounded evidence; production conformance remains
separate. `policy` below means real SQLite/files with explicitly fake AEAD.

| Case | Dated evidence and limit |
| --- | --- |
| P01 | Actual child death inside buffered private write; partial temp pinned while writer lives |
| P02 | Death after durable no-replace link publication, before SQL activation; quiescent cleanup |
| P03 | Before-commit death and two-SQL-connection rollback/activation policy |
| P04 | After-commit death, reopen returns committed complete set |
| P05 | Epoch-change/reset fence rejects a staged stale publisher (policy) |
| P06 | Pair/credential epoch fencing prevents revived grant (policy; final deployment race open) |
| P07 | Two connections cannot activate one writer twice (policy) |
| P08 | Live admitted writer pins staged records; second writer refused (policy) |
| P09 | Dead writer's unreferenced records/strict pending files safely collected on reopen |
| P10 | Death inside new-key write and after staging it preserves old generation |
| P11 | Death after first/all staged rotation records preserves old complete set |
| P12 | Death before/after SQL generation commit selects all old/all new |
| P13 | Death after obsolete-record retirement preserves active key and records |
| P14 | Actual missing/wrong old/new key cases lock without provisioning |
| P15 | Corrupt active/staged record and swapped AAD binding reject activation (policy; earlier real-AEAD controls retained) |
| P16 | Actual death after reset fence; startup/health cannot resume it |
| P17 | Death after replacement-key/before reset commit; new explicit resume required |
| P18 | Real native current-admin/signature plus actual Ingress/Origin/CSRF denials and fresh resume |

The companion/auth/runtime SDDs stay Draft. Separate production budgets
80/82/58 and sixteen live bridge cases are unchanged. Full lease expiry with
live workers, reader/reset/collector concurrency, final adapter/package and
backup/restore, signed-recovery UX/authority review, and owner browser/provider
conformance remain gates. No fixture count substitutes for these gates.

The next supported read-only validation profile is deliberately bounded:
a dedicated App/helper, fixed native Core/My callback, dedicated public PKCE
client and `user-read-private`, App-only grant exchange and one forced refresh,
no import/playback/history migration, no public App callback, manual start and
twenty-minute expiry. Key loss locks the trial; an explicit removal/reinstall
uses a fresh isolated trial namespace. Production reset/renewal management UX
is excluded. A separate template-based SDD, readiness review, exact-package
review, offline provider contract tests and disposable package acceptance must
precede installation on owner HA. Then Chrome must prove native callback,
fresh same-admin completion, account read, refresh and cleanup. This sequence
is a proposed next contract, not implementation permission or a live pass.

## Reproduction and cleanup

Stage the regular `tools/__init__.py` anchor, existing private-file/publication
fixtures, existing `app/server.py`, and both new scripts read-only at `/research`.
Set `PYTHONPATH=/research`, use the pinned image/no network and a fresh labelled
volume at `/data`, then drop to UID/GID 10001 before running either command:

```text
python3 /research/tools/ha_oauth_companion_lab/enrollment_probe.py
python3 /research/tools/ha_oauth_companion_lab/recovery_probe.py
```

Never reuse an existing volume, mount a personal config, expose a host port or
run these tools against a real App. Receipts contain versions, booleans and
source hashes; never retain private keys, challenge values or archive bytes.
CSR teardown checks its exact owned marker, seven permitted files and private
modes/types. Recovery teardown checks all twenty-two current case names/markers, safe
private files and no volume consumers. The first recovery volume contained
72 files / 696,320 allocated bytes; the expanded campaign contained 119 files /
1,118,208 allocated bytes. Both were removed. Earlier CSR iterations each
contained seven files / 45,056 allocated bytes and were removed; the final CSR
iteration contained seven files / 53,248 allocated bytes and was removed using
the same verified guard; the current-source repeat also removed seven files /
53,248 allocated bytes. Both final volume deletions measured zero filesystem
free-space change inside the container. Allocated bytes do not
imply a filesystem free-space increase. The shared pinned image is retained.

Before publishing the sources, the Action's catalog compatibility error again
required a [documented exceptional normal merge](https://github.com/vypdev/symphonia/issues/30#issuecomment-6402126583).
The prepared merge tree equalled develop and all six configured commands passed
(521 existing tests, 89% coverage and 27 UI cases) before a fenced normal push.
No catalog/protection/verification policy was changed.

To reproduce the real-wire campaign, start the guarded lab using
[its guide](ha-app-lab.md). The operator requires a new private receipt folder
whose parent already exists; use that same folder for every command:

```text
python3 tools/ha_oauth_companion_lab/wire_lab_operator.py stage --receipts /private/tmp/symphonia-wire-new
python3 tools/ha_oauth_companion_lab/wire_lab_operator.py install-start --receipts /private/tmp/symphonia-wire-new
python3 tools/ha_oauth_companion_lab/wire_lab_operator.py restart-core --receipts /private/tmp/symphonia-wire-new
python3 tools/ha_oauth_companion_lab/wire_lab_operator.py phase --receipts /private/tmp/symphonia-wire-new
```

Only when phase is `paired`, execute `lose-keys` within 180 seconds, then
`receipt` after `complete`/`failed`. Always execute `cleanup` using the same
receipt folder; it uninstalls only its App, restores exact original config,
removes verified component files, restarts Core, confirms synthetic users are
absent and removes its private namespace. Never dump Core environment/auth,
App info URLs, approval documents or raw requests. Unexpected config/source
changes stop cleanup for manual reconciliation; retain the original backup.
Stop the lab afterwards, preserving its pre-existing volumes.

The successful wire teardown removed twelve owned component sources and ten
bytecode files, ten staged App sources, and nine private Core files (36,864
allocated bytes). Three synthetic users and the entire synthetic App data
folder were verified absent. The lab is stopped. Private receipts retain
versions, assertions, source hashes and failure-stage diagnostics, not keys,
user credentials, callbacks or sessions. The shared image and verification
runtime remain for current review/reproduction.

The separate reset-commit crash iterations each contained seventeen verified
private files / 114,688 allocated bytes and were removed after their receipts
were saved (zero measured filesystem free-space change). No private recovery
material remains in those volumes.
