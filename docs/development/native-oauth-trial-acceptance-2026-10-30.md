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
| Local reproduced App image | `sha256:6e580d539ccf4e2836892181244b03266a222ebacda43f80c9278b804dc6e270` |
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
| Package suite | 8/8, 36.529 seconds | Fresh Core/Supervisor execution, not replayed receipts |
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
pairing forms were reviewed in English and Spanish. Five original captures
(pair forms, pairing success, unchecked consent and confirmed retirement) remain
in the local `symphonia-native-oauth-trial-20261030` review bundle, with a
`browser-capture-manifest.json` inventory. They contain no bootstrap material or
session routes. They are separate review outputs, not shipped App assets or
CI-reviewed source. Copilot refused binary evidence in the source diff; Chrome
attachment upload was unavailable with its current file-access setting. Public
capture delivery and independent visual acceptance remain pending; no check was
waived and file metadata alone does not establish image correctness. The encrypted
backup checkbox was a synthetic acknowledgement, not proof of encrypted lab backups.

Chrome paste alone did not emit the native field-change events in the automation;
ordinary keyboard edits and Tab committed values. No native-action guard was relaxed.
Cleanup initially refused a Python cache created by its own diagnostic import after
Core's header-only cache receipt. That one cache was checked against the exact source
compilation before removal; the cleanup probe now uses Python's `-B` option. A fresh
eight-case package campaign then completed all owned cleanup successfully.

Code review identified duplicate cache receipt entries that could make a second
unlink fail after partial removal. The generated installer now refuses duplicate
paths and missing ownership headers before deleting anything. Package C07 injects
duplicate and empty receipts and checks that every source/cache byte survives;
the valid receipt still permits complete owned removal.

The read-only Ingress used the browser's English language fallback despite the
Spanish HA profile. Its paired-state next action was clarified after this review;
the final English/Spanish wording and narrow layout were subsequently inspected
in Chrome at 390 × 844 with the actual shipping renderer and named synthetic
status/Ingress-header fixtures. Tab focused the read-only link. Staged, active,
verified, locked, uncertain and expired text was also inspected with synthetic
states. This supplements the earlier real authenticated Ingress review; it does
not assert new HA login/cookie semantics or real provider outcomes. Epoch UTC deadlines and the semantic diagnostic presentation
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

Still required: final clean artifact review and remote checks; applicable exact-package installation/Core
restart approval; live dedicated Spotify consent through My, fresh native
confirmation, App restart, confirmed refresh/account match; owned retirement and
separately observed Spotify revocation. No real account, token, verifier, code,
private key, hostname or session route is included in this report.

## Owner preflight rechecked before installation

Read-only Chrome preflight again observed Core 2026.10.4, Supervisor 2026.10.5,
HAOS 18.3, Frontend 20260930.5 and Home Assistant Green. The local backup
location explicitly reports encryption enabled for future backups; the Cloud
location only accepts encrypted backups. No archive or encryption key was opened,
and no backup settings were changed. Existing Terminal provides sh, tar,
sha256sum, base64, wget and curl. The Core configuration marker is present at
`/homeassistant`, and the new helper namespace is absent.

The corrected installer SHA-256 is
`0eec44877099327b976e0fc86a53f57b7040cb51a5ff2aa6a4da1522f7068e9c`.
All eight package cases were freshly repeated successfully with that installer,
including the expanded duplicate/empty-cache receipt checks and complete cleanup.
An earlier repeat stopped during store reload timeout after successful standalone
Core checks; that partial run counted as no completed package suite. Its exact
owned stage was removed before the successful fresh campaign. Laboratory setup
now refuses errors other than that specific timeout and requires the exact named
local App to be available before installation.

Verify adopts the scheduling policy from PR #37 so this candidate's push does not
launch duplicate verification; all existing jobs and permissions are retained.
No new trial package, helper execution, Core restart or Spotify consent has yet
been applied on the owner's installation. Installation still requires exact-package
review and applicable browser action-time confirmation.

A second code-review correction preserves `retired` status after explicit local
retirement and process restart, while ordinary expiry remains `expired` and
backwards-clock state remains `locked`. No grant/channel authority is restored.
The state and HTTP cases exercise these distinctions, and package C08 observes
the real mTLS retirement reply without substituting the response. The final
eight-case campaign passed again and removed all owned artifacts.

The final App manifest SHA-256 is
`45c63d524923fbc60f77c0dd34ba8c09b68ed2e3bfb7ffd793db8f79e587151b`.
Combined coverage was recollected on this source: all twelve changed modules
remain above85%, aggregate92%, pure policy branches100%. Final paired-state
EN/ES screenshots are retained locally, separate from CI source review.
