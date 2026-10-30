# Native OAuth trial: validation on 2026-10-30

The isolated implementation has passed its 54 source/package cases and the
owner's real native Spotify OAuth at `e21afcd` and corrected `852f3ea`, App restart, confirmed refresh/account match
and local retirement in Chrome. Dedicated Spotify access removal was separately
observed. The implementation remains under maintainer review; this bounded
trial does not approve the production companion.
The final owner campaign below validates the corrected payload. Earlier sections
retain their source-specific measurements and historical acceptance boundaries.

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

## Changed-module coverage at e21afcd

This table records the owner-installed baseline; subsequent corrections and
their fresh measurements are recorded below. Coverage combines ordinary tests with actual installed-helper/Core and App
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

Clean artifact review, exact-package installation/Core restart approval and the
live flow have now occurred; see the owner campaign below. Final evidence review
and protected PR checks remain separate gates. No real account, token, verifier,
code, private key, hostname or session route is included in this report.

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
At this preflight stage, no new package, helper execution, Core restart or Spotify
consent had been applied. The subsequent separately approved owner campaign is
recorded below; preflight alone was not installation or live acceptance.

A second code-review correction preserves `retired` status after explicit local
retirement and process restart, while ordinary expiry remains `expired` and
backwards-clock state remains `locked`. No grant/channel authority is restored.
The state and HTTP cases exercise these distinctions, and package C08 observes
the real mTLS retirement reply without substituting the response. The final
eight-case campaign passed again and removed all owned artifacts.

The final App manifest SHA-256 is
`45c63d524923fbc60f77c0dd34ba8c09b68ed2e3bfb7ffd793db8f79e587151b`.
Combined coverage was recollected on this source: all twelve changed modules
remain above85%, aggregate92%, pure policy branches 100%. Final paired-state
EN/ES screenshots are retained locally, separate from CI source review.

## Real owner Chrome campaign

The owner explicitly approved App/helper `0.1.0b1` at source
`e21afcdd12905ec8ad69df509cbb82917a0c47f1`, both Core restarts, the dedicated My
redirect, only `user-read-private`, one bounded trial and its removal. The remote
branch still resolved to that commit immediately before installation. The
installer hash above was checked again on the owner host before installation
and removal. The clean helper ZIP hash is
`b11d94d7a00ce7315a9c75e14e3abff1c9400d2b67b1005e78c81156d0d3bc2c`.
The App was built by the owner's Supervisor from the reviewed store branch;
its Dockerfile verifies the twelve-file source manifest and pinned dependencies.
The laboratory image ID above is not asserted to be the owner's image ID.

| Stage | Directly observed result |
|---|---|
| Owner matrix | Core2026.10.4, Supervisor2026.10.5, HAOS18.3, Frontend20260930.5, Green/aarch64; current owner Chrome |
| Backup preflight | Future local backups report encryption enabled; Cloud accepts encrypted backups only; no archive/key was opened |
| Installation | Distinct native App installed stopped; boot, watchdog and automatic updates off; helper installed after hash check; normal Core check passed and approved Core restart completed |
| Delivery | Existing Terminal has no `/addons` mount; a separate reviewed store branch was registered without expanding Terminal permissions |
| Pair | Native Spanish administrator form accepted the actual prefixed slug, dedicated public Client ID, private one-use block and encrypted-backup acknowledgement; HA reported configuration created |
| Provider/My | Exact My URI saved in the dedicated developer app; Spotify returned using existing dedicated read consent; My selected the owner's already authenticated HTTPS instance |
| Stage | Native HA displayed callback received, no exchange yet, and a new unchecked same-admin confirmation |
| Exchange | New native confirmation completed; HA reported account verification and encrypted App grant |
| Restart/refresh | Only the trial App was restarted; native Reconfigure still offered refresh with the same original deadline; one fresh confirmation reported OAuth, App restart and account match after refresh verified |
| Local retirement | Native confirmation reported channel/grant retired and Core keys cleaned; the integration then showed no entries |
| App removal | App stopped and uninstalled, including its private data; installed Apps list retained the separate older trial and normal services |
| Helper removal | Same exact installer verified source/cache hashes and reported owned source removed; subsequent normal Core configuration check passed |
| Spotify removal | Dedicated test grant disappeared from Spotify Account Apps, connected count changed12 to11, and the separate normal Home Assistant grant remained present |

The App's persisted original deadline was `2026-10-30T17:12:33Z`; pairing,
callback, exchange, restart, refresh, local retirement and App removal completed
before it. Restart did not extend it. This campaign reused existing provider
consent and does not claim a fresh Spotify permission checkbox appeared. It
proves the real authorized round trip and explicit native App mutations, not
continuity with an original browser login. No provider write/playback was run.

HA opened its provider tab automatically. The operator also opened the external
link once, creating a second authorization tab; it was closed before callback
delivery. Only one return was delivered and one exchange/refresh confirmed.
The runbook now directs the operator to continue the automatically opened tab.
After Core restart an old Terminal iframe stayed at `Reconnecting`; reloading
Ingress restored the actual shell prompt. No Terminal restart, new mount,
credential, protection change or extra host privilege was used.

Local screenshots capture the native verified and retired results without grant
material. They remain private review artifacts, outside the source diff. The
bounded trial's operator result is separate from independent visual review,
broader accessibility/browser acceptance and production readiness.

After the post-removal configuration check passed, the empty owned Core key
directory and the separate trial store registration were removed. The approved
second Core restart completed successfully and authenticated Terminal Ingress
returned. Final checks observed the helper and private-key namespace absent.
Only the exact hash-matching installer and its ownership marker were deleted;
the staging directory was then removed empty. Normal HA services and the older
stopped research App were preserved. The dedicated developer app retains the
registered My URI for future explicit tests; its Spotify account grant is revoked.

## Post-live enrollment rollback correction

Review of the evidence commit found that certificate preparation followed the
durable pairing commit. A local CA read/signing error could therefore consume
the bootstrap without delivering credentials. Enrollment is now a semantic
transaction scope: the use case prepares the certificate inside it, SQLite
commits only when preparation succeeds, and the in-memory challenge is cleared
only after commit. No certificate response escapes a failed commit.

Case native-trial-adapter-C03 now uses real loopback TLS and injects CA read,
signing and SQLite COMMIT failures. Each failure preserves the complete original
metadata and challenge with no transaction left open. Reopening the real files
preserves the original identity, bootstrap window and deadline; subsequent valid
enrollment works. This adds no recovery endpoint or replay permission. A lost
response after successful commit still requires retirement; the native form
continues to direct owned reconciliation for partial Core material.

The full ordinary suite again passes 616 tests with 8 explicit skips; the fresh
eight-case package campaign passes in30.781 seconds and removes its App, helper,
source stage and backup. The corrected App manifest is
`35524ae01146f727be843d76dce6ed9abf643f0236069037d32607e973e530ae`;
the reproduced local image is
`sha256:7e55cdf654674f0ac64ff5947b6125b114b45201b1c53d5937579a558da68a4b`.
For that enrollment-only correction, Core helper/installer bytes and their hashes
were unchanged. Root coverage is89%.
Fresh unit, installed-helper/Core, App child-process and shipping-image fragments
give92.3% combined coverage; each of the twelve modules exceeds85% and pure
policy branches remain100%. The real shipping image again proves UID10001,
identity/deadline persistence, missing-key lock and read-only startup failure
with external networking disabled. Protected review remains pending.

The real owner result above applies to the exact earlier manifest, not this
corrected image. The owner instance remains clean. A further exact-package owner
run must be reviewed and explicitly approved before another installation and
Core restart; no previous deadline, grant or consent is silently reused.

## Campaign cleanup and installer interruption corrections

Further review identified two tooling failures: a campaign exception could skip
retirement, and a cleanup-only signal trap could resume the shell afterward.
The campaign now records acquisition boundaries and attempts cleanup in a
`finally` block, including copy/install, helper and backup-inspection failures.
A returned backup slug is recorded before archive inspection. Existing source
hash/ownership checks remain mandatory; unacquired, unknown or modified objects
are preserved. Missing helper state is allowed only as a confirmed absent
artifact. An ambiguous backup acknowledgement is explicitly unconfirmed and
never triggers name-based deletion. Original failures survive cleanup errors;
an incomplete receipt never counts as a passing campaign.

Installer EXIT cleanup is separate from HUP/INT/TERM handlers, which exit129,
130 and143. Case native-trial-package-C07 executes the generated bytes in the
pinned Core's POSIX shell with test-only command pauses. All three signals are
tested after atomic publication and before the first unlink. Interrupted
publication never reports success; interrupted removal performs no later
unlink. Already published source is retained for hash-owned reconciliation,
not claimed rolled back. A negative fixture with the prior trap reproduced its
false-success behavior. Eight mocked acquisition/cleanup failures and two
absence-error guards supplement the actual Supervisor campaign; those mocked
ports do not count as real Supervisor failure observations.

The final ordinary suite passes 616 tests with 8 explicit skips. The fresh full
package campaign passes8/8 in30.817 seconds, reports completed=true and confirms
cleanup of its App, source stage, helper, known backup and exact temporary
installer. Its signal result is true. The corrected installer SHA-256 is
`92856d6fdd9a7e6ee70215f831f9d305ceea5bd4ce2567c7e8f34ef84ea74db4`.
The helper ZIP/source bytes and App manifest/image remain those recorded in the
enrollment correction: the App/Core Python coverage above measures identical
source bytes. The owner live result remains tied to `e21afcd`; this final
package has laboratory evidence only and has not been reinstalled on owner HA.

## Import guards and shipping-resource failure cleanup

The next review exposed two test-harness gaps. Case native-trial-http-C06 now
collects both AST import forms, imported children and original alias names. Its
negative fixtures reject direct/from/aliased native Spotify and Supervisor
imports, aliased default OAuth helpers, pure-layer framework/SQLite imports and
qualified or relative infrastructure adapters. Allowed domain/standard-library
imports still pass. This is a declared-import boundary check; the real-Core
default-token-path traps remain separate runtime evidence.

The shipping supplement now claims fresh volume/container names and cleans them
in a resource scope on success or failure. Removal checks the exact name, owner
label and expected image ID; foreign/modified resources are preserved. Volumes
are removed without force after owned containers, and cleanup failures preserve
the original error and an incomplete receipt. Container creation is tracked
before the call, including the temporary key-removal utility. Checks run the
inspected immutable image ID. The Core peer-key probe also uses a disposable
temporary-directory scope on every exit.

Case native-trial-package-C07 now injects failure after real Docker volume
creation and after an attached container starts, verifying both are absent
afterward. A separately labeled metadata fixture refuses deletion of a foreign
owner. The actual shipping supplement again reports completed=true, owned
resources removed, UID10001, restart identity/deadline persistence and both
locked/read-only startup failures. No provider network is enabled.

The ordinary suite passes 616 tests with 8 explicit skips; the fresh integrated
campaign passes8/8 in26.744 seconds, including these failure probes and complete
owned cleanup. App, helper payload and installer bytes are unchanged from the
preceding correction (`35524ae0` App manifest, `92856d6f` installer). The measured
production-module coverage therefore still applies to identical source bytes.
The real owner proof remains specifically `e21afcd`; protected review and a new
exact-package owner run remain outstanding for the corrected candidate.

## Revocation confirmation and full helper preflight

Unexpired native entry removal now requires the App's revoke result to report
`retired` or `expired` before deleting Core pairing keys. Missing, pending,
malformed or transport-unknown replies preserve actual key files and report
retirement pending. The normal native retirement flow also rejects non-string
phases safely. Installed-helper/Core fault probes exercise empty, null, array,
object, active and failed replies plus confirmed retirement/expiry; actual key
hashes remain unchanged for every unconfirmed outcome. These App replies and
request actors are named fault fixtures, separate from the real TLS/admin proof.

The installer now exposes read-only `verify`, reusing the complete removal
preflight before any mutation: every source digest, allowed entry, owner/link
invariant and recorded runtime cache is checked. The Supervisor probe runs this
gate before importing either fresh or existing helper code and disables new
bytecode writes. A receipt digest alone is no longer treated as payload proof.
Case native-trial-package-C07 confirms that verification changes no bytes and
refuses modified payload and unexpected files while preserving them.

The DNS deadline fixture waits for its real loopback datagram before advancing
the scheduler. Its outer safety timeout is now 20 seconds, longer than the
request's own 10-second deadline, so it cannot cancel the request first under
ordinary scheduler delay. The transport remains unchanged; the fixture still
requires `TrialError(uncertain)` and completed resolver cancellation/closure.

The full ordinary suite again passes 616 tests with 8 explicit skips. A fresh
eight-case campaign passes in 40.336 seconds with completed=true and all owned
cleanup categories confirmed. Coverage was recollected from current unit,
installed-helper/Core, child-App and shipping-image execution: all 12 production
modules exceed 85%, aggregate 92.55%, Core lifecycle 93.33%, pure branches 100%;
root coverage remains 89%. No earlier helper fragments were merged.

The current installer SHA-256 is
`b06b9d44bcac5eb569407feb08681b0ed46f5098487a6bf37ccf96596255b099`;
the helper source-manifest SHA-256 is
`ae4834fdd01f90863229786855981bf6a0ea08fc488194a3f8280ac295053707`.
The App manifest/image are unchanged (`35524ae0`, `7e55cdf6`). This corrected
helper/installer initially had laboratory evidence only. The following separately
approved campaign supplies owner acceptance for those exact corrected bytes.

## Corrected owner campaign at 852f3ea

The owner explicitly approved installing App/helper `0.1.0b1` at
`852f3eaca190c16f94a2f30290a875d2a10bfe4c`, two Core restarts, one bounded
read-only provider campaign and complete owned retirement. Core 2026.10.4,
Supervisor 2026.10.5, HAOS 18.3 and Green were rechecked. Future local backups
were visibly encrypted; no archive or encryption key was opened or changed.
Helper/key/staging namespaces and the App were absent before installation.
Spotify showed no dedicated trial grant and preserved the normal HA grant.

The reviewed branch head was checked at `852f3ea`; the separate store source was
registered and the App rebuilt before manual start. The self-contained installer
matched `b06b9d44` (full digest above). Install and read-only `verify` both passed.
Core's normal configuration check and first restart completed. Boot, watchdog,
automatic update and sidebar remained off. The unchanged twelve-file App
manifest was `35524ae0`; helper manifest `ae4834fd` and ZIP `6e72e43a`.

The real Chrome flow passed these observations:

1. Native pairing accepted the actual repository-prefixed slug and private
   one-use bootstrap. The original deadline was 20:30:02 UTC; restart retained it.
2. Spotify visibly presented a new consent screen. Its actual authorization
   request used the dedicated public client, exactly `user-read-private`, S256
   and `https://my.home-assistant.io/redirect/oauth`. Agree was submitted once.
3. One automatically opened provider tab returned through My to the selected
   owner instance. The native form reported callback received but not exchanged
   and required a new unchecked initiating-administrator confirmation.
4. One fresh confirmation produced the native account-verified/encrypted-grant
   result. Restarting only the App then completed successfully.
5. A new native refresh confirmation performed its single renewal. HA reported
   native OAuth, App restart and account match after renewal verified. No token
   was read from Core, the provider UI or App storage.
6. Native retirement confirmed local channel/grant retirement and Core-key
   cleanup. Entry removal left no entries; the App was stopped/uninstalled.
7. Spotify separately confirmed removal of the dedicated grant: connected apps
   returned from twelve to eleven and the normal Home Assistant grant remained.
8. The exact installer verified all source/cache bytes before owned removal.
   The second Core configuration check passed. The empty key namespace, exact
   two-file staging directory and separate store registration were removed;
   the final Core restart completed after those checks, and the frontend returned.

Pairing, exchange, restart, refresh, local retirement, App removal and dedicated
provider revocation finished before the original deadline. Three representative
original local captures and a sanitized receipt identify this campaign; no binary
capture or private hostname is committed. An operator observation accidentally
printed an encoded temporary callback link in local tool output. It was not
written to repository evidence; the code completed once through the normal
confirmation path and dedicated provider access was subsequently revoked.

This is bounded real OAuth acceptance for the corrected payload, separate from
laboratory fault/backup-restore evidence. No owner backup restore, original-login
session continuity, broader scope, library import, playback or production rollout
is claimed. Formal human review and normal protected merge remain outstanding.
