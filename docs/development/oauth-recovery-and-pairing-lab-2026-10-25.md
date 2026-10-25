# Native OAuth recovery and CSR pairing laboratory

**Date:** 2026-10-25. **Status:** bounded research for issue #30, not production
implementation or an owner-Home-Assistant pass. PR #29 is merged in develop at
`818a50e153ddee0b0569ed2bba6373c29b1bd2f3`; its approved head and merged tree
match. Its PR CI producer passed all seven jobs before merge.

## Environment and boundaries

Both opt-in campaigns use the official Core 2026.10.3 image pinned to
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

Thirty Boolean observations pass across these fourteen distinct scenario groups:

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
| C12 | Explicit renewal switches the exact serial/key; old identity fails; lost acknowledgement returns the same public result |
| C13 | Revocation, changed epoch and OAuth/playback profile separation deny stale authority; explicit re-pair uses the new epoch |
| C14 | Three actual process deaths recover admitted/uncommitted/committed issuance correctly |

C14 deliberately exits child processes with `os._exit(83)` after challenge
consumption, before the certificate SQL commit and after commit/before an
acknowledgement. Reopen/status cannot mint a certificate. Pending issuance
cannot be replaced by a fresh challenge; explicit resume completes the admitted
request once, while a committed result remains stable. Public result retrieval
conveys no private-key possession. Pending-epoch revocation races remain part of
the full native lifecycle conformance gate.

Renewal policy is exercised directly, and the resulting certificate crosses
TLS. Enrollment/renewal over the complete native Core-to-Supervisor wire,
native setup authorization, concurrent deployment lifecycle, Core key-file
publication and final package compatibility remain unproven. The fixture's
per-challenge counter is not a certified global per-minute rate limiter.

## Multi-record rotation and reset ordering

[The recovery fixture](../../tools/ha_oauth_companion_lab/recovery_probe.py)
uses three separately bound synthetic credential records and a complete active
reference set. A durable writer admission precedes file staging; an SQL switch
activates the entire set and key generation together. A live admitted owner
conservatively pins staged files. Collection holds the SQL admission fence and
does not use file age as evidence of terminal ownership.

Fourteen actual process deaths pass with real AES-GCM:

| Operation | Interruption points |
| --- | --- |
| Publish, 4 | Before a record, after the first staged record, before commit, after commit |
| Rotate, 6 | New key staged, first record staged, all records staged, before commit, after commit, obsolete records retired |
| Explicit reset, 4 | Durable reset fence, replacement key staged, before reset commit, after commit |

Reopen sees all old or all committed new records, never a mixed active set.
History survives. Reset remains `reset_pending` after an interrupted fence;
health/startup do not create a key or finish the reset. Explicit resume produces
an unpaired identity with no grant and requires new pairing/consent.

The reset caller is an explicitly named **test authorization stub**, not an
HTTP route or proof of a current HA administrator. No real API may turn a
submitted boolean into that authority. Native Ingress, Origin/CSRF, active-user
checks and unauthorized reset requests still need their own real-framework
proof. The fixture cannot claim external provider revocation.

Nineteen [ordinary tests](../../tests/test_ha_oauth_recovery_fixture.py) use
real files/SQLite and an explicitly fake codec. They cover owner/collector and
two-connection races, complete-set activation, partial writes, rollback,
epoch/reset fencing, corrupt/missing old/new keys or records, connection-bound
AAD, lost reset progress, health observation and preserved history. These are
policy evidence, not cryptography or native authorization evidence.

## Fresh native administrator approval prototype

[The native reset prototype](../../tools/ha_oauth_companion_lab/native_reset_probe.py)
boots a separate Core 2026.10.3 with fresh temporary configuration, synthetic
users and real authenticated native config-flow HTTP endpoints. It imports no
owner configuration, Supervisor token or browser credential. Twenty-two Boolean
observations pass: fresh same-admin begin/confirmation, non-admin/different-admin/
inactive-user/revoked-login denial, typed short-lived signed approval, changed
purpose/signature/expiry/replay denial, local reset once and preserved history.
No config entry or approval/private key is saved. Missing, malformed or substituted existing Core keys
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

Eleven additional [ordinary parsing/binding cases](../../tests/test_ha_native_reset_fixture.py)
cover duplicate/oversized fields, current actor/install/profile, typed/bounded
epochs, exact purpose/identifier and expiry. They do not use cryptography or
substitute for real native HTTP. The integrated suite passes **551 tests, no
skips**; combined application coverage remains 89%, with the unchanged 85% floor.
The final native source was repeated after its parser guards; all twenty-two
observations pass. The container and all temporary users/config/key state are
removed with its temporary files and `--rm` lifecycle.

## Fault-plan progress and remaining gates

Relative to the [18-case plan](../architecture/local-key-custody-rfc.md#fault-campaign-plan-18-distinct-cases-bounded-follow-up-results-below),
P02–P04/P09–P13 now have three-record process-death observations. P05–P08 and
P14–P15 have additional policy/fence evidence, with crypto checks retained from
the earlier campaign. P16–P17 prove reset ordering with stubbed admission only;
P18 has a real fresh-native-actor/signature prototype, while its actual Ingress/browser admission remains open. Partial writes *inside* fsync,
lease expiry under live workers, reset/reader/collector concurrency, the final
adapter/backup package and all native/browser/provider paths remain gates.

The companion/auth/runtime SDDs stay Draft. The separate 80/82/58 production
budgets and 16 live bridge cases are unchanged. Passing 30 CSR and 22 native observations,
14 recovery process deaths and 30 ordinary policy cases does not count as those production cases
or authorize treating an unreviewed artifact as ready on the owner's HA.

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
modes/types. Recovery teardown checks all fourteen case names/markers, safe
private files and no volume consumers. The measured recovery volume contained
72 files / 696,320 allocated bytes and was removed. Earlier CSR iterations each
contained seven files / 45,056 allocated bytes and were removed; the final CSR
iteration contained seven files / 53,248 allocated bytes and was removed using
the same verified guard. Allocated bytes do not
imply a filesystem free-space increase. The shared pinned image is retained.

Before publishing the sources, the Action's catalog compatibility error again
required a [documented exceptional normal merge](https://github.com/vypdev/symphonia/issues/30#issuecomment-6402126583).
The prepared merge tree equalled develop and all six configured commands passed
(521 existing tests, 89% coverage and 27 UI cases) before a fenced normal push.
No catalog/protection/verification policy was changed.
