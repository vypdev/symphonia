# Native OAuth trial: validation on 2026-10-30

The isolated implementation has passed its 54 source/package cases. It remains
under review. Chrome laboratory pairing and retirement have passed;
owner-instance/live Spotify acceptance is **pending**. No new trial package or Core restart has been applied to the
owner's Home Assistant during this implementation campaign.

The [SDD](../../specs/native-oauth-validation-trial.md) was marked Ready and its
review committed before implementation began. The catalog remains `proposed`.
Broad production companion/authorization/runtime specifications remain Draft.

## Artifact and runtime identities

| Item | Observed identity |
|---|---|
| App/helper | `0.1.0b1`; manifests and installer generated from the source in this change |
| Official Core image | `sha256:23f4dfbb69ce76315dbc4de7915504f1c2dcecd7ca2648113a493a385972e133`, Core 2026.10.4 |
| Guarded Supervisor | 2026.10.5, aarch64, unsupported devcontainer environment; not HAOS hardware proof |
| Devcontainer image | `sha256:81ea6e6892125d08e88b5a873c12da00131dfc3a184d335179576ec60bc0ecb0` |
| App Python base index | `sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8` |
| Local reproduced App image | `sha256:024b797f8eb9d368ce1ed7e479bf287c1958737c0d0a06063300829a55afd130` |
| Host quality runtime | Python 3.11.15, coverage 7.16.1 |
| App runtime | Python 3.14.10; fifteen pinned dependencies in the App requirements |

The image ID records this local build, not a published release. The final
clean-tree artifact receipt must be generated after committing; do not install
an earlier dirty-tree laboratory export on the owner instance. The source
manifest covers twelve App files; the helper manifest covers eight source files.

## Executed acceptance

| Area | Result | Evidence boundary |
|---|---|---|
| Pure policy | 12/12 | Exact target, redirect, scope, bounds, deadlines and immutable binding |
| State | 12/12 | Actual SQLite; explicit fake provider/cipher for application-state cases |
| Adapters | 12/12 | Actual AEAD, files, CSR/TLS, c-ares timeout/cancellation; controlled provider responses |
| HTTP/UI contracts | 10/10 | Actual local HTTP plus named actor/Ingress fixtures; semantic/localization assertions are not manual UX review |
| Package suite | 8/8, 26.834 seconds | Fresh Core/Supervisor execution, not replayed receipts |
| Shipping-main supplement | Passed | Actual entry module, network disabled, new Linux volume; read-only coverage instrumentation |

The package suite observes each of the following:

1. Real Core HTTP denies unauthenticated, ordinary, different, disabled and
   revoked-session actors. A newly authenticated initiating administrator can
   confirm. This proves a new same-admin action, not original-session continuity.
2. The installed helper's main reconfigure flow generates official public PKCE
   with S256, exact My redirect and fixed scope. Core-signed simulated callbacks
   stage only; no exchange occurs before a new confirmation.
3. Actual Supervisor private alias, CSR, server pin, issued client certificate
   and mTLS work. Wrong pins/pairs, raw operations and unauthenticated private
   RPC are refused. The actual service UID is 10001; no App host ports exist.
4. Same-source native/TLS composition with a test-only Provider port performs
   one exchange/account check and commits a sealed grant. Core default token
   resolution and OAuth session refresh paths are trapped and never called.
5. A new App process reopens the same identity/deadline and sealed grant. A new
   native confirmation performs one refresh and compares the same synthetic
   account. Completed operations do not repeat provider calls.
6. A real Supervisor App-only backup contains six regular metadata/data files,
   zero OAuth key files and no plaintext synthetic access/refresh grant. After
   uninstall/restore, the shipping entrypoint exits 78 with `locked`; the same
   sealed grant/deadline remain and no key is regenerated. This backup is
   unencrypted disposable laboratory data, not evidence about owner backups.
7. The exact shell installer installs/removes only its namespace. Existing,
   modified and unexpected sentinels stop overwrite/removal and preserve unrelated
   files. Formal-suite cleanup removes its App, source stage, helper and backup.
8. Restart preserves retirement and the original deadline. Listener shutdown
   occurs at expiry without rebootstrap or provider replay. A separate fresh lab
   installation isolates expiry from retirement; no host clock is changed.

The installer initially exposed a BusyBox checksum-comment incompatibility;
verification now strips only the ownership header before checking payload hashes.
Real Core testing also caught a positional PKCE-constructor mismatch; named
arguments now match the official public API. Both are corrected in the tested
source. Neither defect was exercised on the owner installation. CI subsequently caught
a JSON-depth test depending on CPython recursion behavior. Both protocol decoders
now enforce 32 containers and reject non-finite values explicitly, with boundary
cases; the full eight-case package campaign was repeated on the corrected source.
The fixed provider transport now requests identity encoding explicitly while
preserving authorization headers; compressed responses and redirects still fail closed.

## Actual Chrome laboratory review

The local Docker laboratory, separate from the owner's installation, served
the real Core frontend and Supervisor Ingress to Chrome. A synthetic administrator
paired the installed helper and App through native forms. HA showed success and
the authenticated App Ingress changed to `paired`, hiding the bootstrap block.
The native Spotify confirmation was inspected with its checkbox unchecked;
Spotify was never opened. Native retirement then confirmed local channel/grant
retirement and Core-key removal. The entry, App and owned source/helper files
were removed, and absence of this installation's Core keys was verified.

Keyboard submission and checkbox operation were exercised at 390 × 844. Native
pairing forms were reviewed in [English](evidence/native-oauth-trial/en-narrow.png)
and [Spanish](evidence/native-oauth-trial/es-narrow.png); representative evidence
shows [pairing success](evidence/native-oauth-trial/pair-success-es.png), the
[unchecked consent screen](evidence/native-oauth-trial/connect-review-es.png), and
[confirmed retirement](evidence/native-oauth-trial/retire-success-es.png).
These images contain no bootstrap material or session routes. The encrypted
backup checkbox was a synthetic acknowledgement, not proof of encrypted lab backups.

Chrome paste alone did not emit the native field-change events in the automation;
ordinary keyboard edits and Tab committed values. No native-action guard was relaxed.
Cleanup initially refused a Python cache created by its own diagnostic import after
Core's header-only cache receipt. That one cache was checked against the exact source
compilation before removal; the cleanup probe now uses Python's `-B` option. A fresh
eight-case package campaign then completed all owned cleanup successfully.

The read-only Ingress used the browser's English language fallback despite the
Spanish HA profile. Its paired-state next action was clarified after this review;
the updated English/Spanish status is covered by HTTP cases, not a second manual
Ingress review. Epoch UTC deadlines and the semantic diagnostic presentation
remain explicit trial limitations. This is partial manual acceptance, not a
complete production UX or accessibility assessment.

## Changed-module coverage

Coverage combines ordinary tests with actual installed-helper/Core and App
process runs, using verified source-path mappings. App instrumentation is
laboratory-only. No changed production module is omitted.

| Module | Combined line/branch coverage |
|---|---:|
| Core entry/lifecycle | 89% |
| Core bridge | 93% |
| Core native flow | 89% |
| Core protected keys | 96% |
| App application | 94% |
| App protected files/AEAD | 95% |
| App provider | 96% |
| App runtime | 88% |
| App HTTP/TLS dispatch | 92% |
| App state | 87% |
| App TLS identity | 89% |
| App pure policy | 100%, including all branches |
| Aggregate | 92% |

All changed modules exceed the unchanged 85% floor. Root repository coverage and
final remote checks are separate gates; see the PR's verification results.

## Evidence limits and remaining acceptance

The ordinary and package cases total 54 distinct cases, not 54 live Spotify
operations. The earlier 22 native-hook and 36 recovery-research observations are
separate feasibility evidence and count as zero final-package cases. Research
was rerun after matching the official PKCE signature; the current source digest
is recorded in the hook report.

In the standalone Core campaign, Docker maps the fixed private alias to loopback;
the Supervisor campaign proves the actual alias separately. Supervisor Ingress
identity headers in the automated campaign are synthetic. The separate Chrome
review above observes actual authenticated Ingress, without proving continuity
with the initiating browser login session. The real Core My component runs, but the external My relay/browser is
not visited by the offline campaign. All provider grants/accounts are synthetic.

Still required: final exact-package status review; clean artifact review and remote checks; owner version and
encrypted-future-backup preflight; applicable exact-package installation/Core
restart approval; live dedicated Spotify consent through My, fresh native
confirmation, App restart, confirmed refresh/account match; owned retirement and
separately observed Spotify revocation. No real account, token, verifier, code,
private key, hostname or session route is included in this report.
