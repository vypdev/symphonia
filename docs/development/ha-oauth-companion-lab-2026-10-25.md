# OAuth companion laboratory results

**Date:** 2026-10-25. **Work:** [issue #26](https://github.com/vypdev/symphonia/issues/26),
[PR #27](https://github.com/vypdev/symphonia/pull/27). **Authorization:** owner
requested laboratory validation of native hooks, pairing and key/backup
protection before implementation. No personal HA instance or Spotify grant was
used or changed; no Cloudflare/public callback was opened.

## Environment and evidence boundaries

The existing image/label-guarded `symphonia-ha-lab` was resumed, with its named
volumes retained. Core was **2026.9.4**, Python **3.14.6**, Supervisor
**2026.10.4**, on the existing macOS/OrbStack ARM64 devcontainer. The Core
image ID was `sha256:dd1ad589936601cacb1b4797d17e27ce762b5147fb46b0e8e3d5486ab95e56c3`.
Core's installed cryptography package was **48.0.1**. The research App used
the pinned Python base in its Dockerfile, with no additional dependency install.
This unsupported-for-production Supervisor devcontainer is not an HAOS/hardware
security or supported-version matrix pass.

The native HTTP experiment also passed separately on official **Core 2026.10.3**
in a networkless container, matching the version previously observed on the
owner's installation without accessing it. Its immutable image reference is
`ghcr.io/home-assistant/home-assistant@sha256:407b89cd11a8cb67d388d21739a226c74acbbebe1ac59e3b83b11b43ce76b98f`,
with local ARM64 image ID
`sha256:d1733a7dbfb6c42a837ee00f18f1d97b65e5aa55554ad6e505bbc56e08e385a9`.
That image reported Python **3.14.9** and cryptography **50.0.1**.
The actual Supervisor/App transport and backup experiments used the 2026.9.4
lab Core; the 2026.10.3 result is the isolated HTTP/storage experiment only.

The [reproducible sources](../../tools/ha_oauth_companion_lab/README.md) produce
three deliberately separate observations:

- Native HTTP hooks: a new Core process from the exact image, **network none**,
  fresh tmpfs config, generated users, cleared environment and no mounted live
  HA data. It runs actual native auth/config-flow/callback endpoints; it is not
  a mock of those framework objects or an installed production integration.
- Transport: a real request from the running disposable Core container to a
  newly installed Supervisor-managed research App's internal DNS alias, using
  pre-issued synthetic X.509 credentials, SPKI pinning and TLS 1.3.
- Backup: actual Supervisor partial archives, with selected synthetic Core/App
  canary records, protected/unprotected archive reads, and restoration of the
  **research App only**. Core was never restored.

Backup API calls used the disposable Core's existing Supervisor service token
only in memory against the local Supervisor, without redirects or value output.
That is distinct from the generated provider/key canaries; no personal/provider
credentials were used.

## Native hooks: bounded pass

| Observation | Result |
| --- | --- |
| Unauthenticated native begin | HTTP 401 |
| Non-administrator native begin / confirm | HTTP 401 / 401; no completion |
| Main reconfigure flow, native OAuth callback dispatch | Passed |
| Background reauth waits for a fresh authenticated native request | Passed |
| Two per-attempt authorizers | Distinct S256 challenges/verifiers |
| Wrong state / valid synthetic callback | HTTP 400 / 200 |
| Callback's actor and effect | No admin actor; return staged only |
| Another administrator on confirmation | Rejected from the freshly observed actor; original flow not consumed |
| Initiating administrator confirms | Safe synthetic result committed; no provider exchange |
| Disabled user / revoked refresh-login token | Fresh native POST denied with HTTP 401 / 401 |
| Config entry and saved config files | Safe references only; generated code/verifiers absent after shutdown |

The fixture overrides the public main config-flow completion step; it neither
patches Core nor calls the default token exchange/storage path. The current
actor is read from Core's server request context, not from submitted form IDs.
These results support the **feasibility** of the RFC's native hook shape on
2026.9.4 and 2026.10.3. They do not establish browser UX, a complete supported deployment matrix,
same-browser/original-login continuity, mid-flight global revocation, or a
real Spotify connection. An authenticated request admitted before revocation
is not retroactively cancelled by this claim.

## Private pairing/transport: bounded pass

The actual alias `local-symphonia-oauth-lab-transport` resolved from Core. Docker
reported `{}` host port bindings and bridge networking. The fixture has no
Core/Supervisor API grants or extra mounts; metadata is staged only in the lab,
and its repository filename `app-metadata.fixture.json` prevents ordinary
App-store discovery. Supervisor 2026.10.4 scans
[`**/config.*` with a supported extension](https://github.com/home-assistant/supervisor/blob/2026.10.4/supervisor/store/data.py#L157-L163),
so `config.fixture.json` would still be discovered; the final fixture name avoids
that pattern and a regression assertion checks its source directory.

| Real TLS request | Observation |
| --- | --- |
| Wrong server SPKI pin | Rejected before sending the enrollment body |
| Unenrolled client / wrong challenge | HTTP 403 / 403 |
| Valid one-use enrollment / paired hello | HTTP 200 / 200 |
| Replayed enrollment | HTTP 403 |
| No client certificate / other signed client | HTTP 403 / 403 |
| Wrong epoch / protocol version | HTTP 403 / 403 |
| Playback profile / player command | HTTP 403 / 403 |
| Unknown field / management routes | HTTP 400 / 404 |
| Pair revocation / previously valid client | HTTP 200 / 403 |

The test CA and leaf certificates were generated before enrollment. Therefore
this is **not** proof of production CSR issuance, certificate renewal, durable
pair enrollment, user-facing fingerprint comparison or protected key persistence.
The fixture uses certificate identity on its server and SPKI pinning on its
client; final rotation semantics remain a protocol review item. The synthetic
challenge expires at 300 seconds in deterministic tests and its on-disk copy is
consumed at startup, so a fixture restart cannot silently re-arm it.

## Keys and backups: positive mechanism, unsafe baseline exposed

| Experiment | Observation / limit |
| --- | --- |
| Actual HA `Store(private=True)` | Mode 0600, but generated key canary remains plaintext |
| Supervisor backup without password | Selected Core `.storage` and App plaintext controls are readable after normal archive decompression |
| Supervisor protected backup | Correct password restores the controls; wrong password is rejected |
| App `backup_exclude: ["excluded/*"]` | Key directory absent from the actual App archive |
| AEAD sealed fixture in an unprotected archive | Contains no plaintext key canary; external wrapping key decrypts it |
| Wrong wrapping key, modified ciphertext or playback-domain binding | Rejected by authenticated decryption |
| Actual restoration of only the research App | Excluded keys absent; App reports `locked_after_restore_or_unprovisioned` and exits/stays stopped |

File permissions, record encryption and archive encryption are **three distinct
controls**. Private HA storage is not a sealed key store merely because the
file is owner-readable. Protected Supervisor archives do not encrypt the live
Core file. The AES-GCM experiment uses a synthetic wrapping key outside the
copied record; it is not acceptance of a production crypto/key-management stack.

The key source remains a blocker: no protected persistent HA wrapping-key
facility, secure cold-start/unseal, hardware-backed storage or cross-install
restore/rotation policy was proved. App backup exclusion works, but intentionally
losing a required key means restore cannot automatically recreate pairing.
Production must specify this operator recovery path and test the complete
secret-store publication/refresh/disconnect lifecycle. No `.storage` plaintext
fallback is accepted by these results.

## SDD/matrix implications

The [companion SDD](../../specs/home-assistant-oauth-companion.md) remains **Draft**.
`RG-008` now has bounded native-hook, transport and App-backup evidence instead
of only a proposal; remaining key, lifecycle, supported-version and browser
proof is explicit. The existing authorization/runtime budgets remain 82/58;
the companion's 80 cases are still a planned production budget.

| Live matrix area | Updated status |
| --- | --- |
| L01, L14 pairing/isolation | Partial: actual internal TLS/negative cases; no full production enrollment/rotation |
| L05–L07 native actor/confirmation | Partial: real framework HTTP with synthetic users; no production App exchange or browser pass |
| L08, L10 state/PKCE | Partial: native wrong-state check and independent authorizers; no real provider exchange |
| L15 backup | Partial: native archives, AEAD controls and App-only restore; production key custody and complete restore remain open |
| L02–L04, L09, L11–L13, L16 | Not established by these experiments; prior direct-tunnel/loopback results do not fill them |

## Verification and cleanup

The later PR #27 review correction adds a two-second idle timeout before each
accepted socket's TLS handshake and HTTP parsing, and rejects a missing client
certificate before reading a POST body. Four additional loopback tests cover
stalled real TLS handshakes, stalled HTTP headers/bodies and early certificate
denial. HTTP-only cases replace TLS wrapping; these tests do not establish a
complete slow-drip, concurrency or denial-of-service bound. The original run
below predates that correction; its real TLS route is repeated separately.

The corrected Supervisor fixture was installed again with fresh synthetic PKI.
The actual Core-to-App TLS 1.3 route passed all original pin/mTLS/enrollment/
revocation assertions, plus the reproducible `transport_probe.py stalls` cases:
an idle real handshake closed; a later valid request was served after stalled
headers and body; missing client certificate returned 403 without a body.
No provider call or owner-HA modification occurred. The review revision passes
**480 tests and 89% coverage**. Twelve successor key-custody tests are separate
work for issue #28 and are not included in that PR #27 total.
The repeated App was then uninstalled; its three staged files were removed
after exact source-hash comparison and its marked 14-file synthetic PKI was
removed. No new backup was created in this transport-only repeat. The guarded
lab was stopped again with its pre-existing named volumes retained.

The **10 fixture-policy tests** cover expiry at the boundary, wrong/replayed
challenge, certificate/epoch revocation, missing identity, version/type/profile
confusion, arbitrary operations/fields and artifact permissions. They are
research regressions, not a substitute for real framework/TLS/archive evidence.
The original campaign, before the review follow-up above, passed **476 tests**, with **89%** combined line/branch
coverage against the unchanged 85% floor. Specification validation, whitespace
and manual SDD/catalog consistency checks passed.

Both main probe archives were removed; the correct Supervisor
`DELETE /backups/{slug}` cleanup route was separately checked with a minimal
backup, also removed. Final count of owned probe backups was zero. The exact
Core control file and two marked synthetic PKI directories were removed. The
research App was uninstalled; its staged sources were removed only after byte
comparison with the checkout. The guarded lab was stopped, its original named
volumes retained. No production source, dependencies, workflows or owner-HA
configuration changed.
