# Native OAuth trial: validation on 2026-10-30

The isolated implementation has passed its 54 source/package cases. It remains
under review; manual browser review and owner-instance/live Spotify acceptance
are **pending**. No new trial package or Core restart has been applied to the
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
| Local reproduced App image | `sha256:91c3ec2d17a8a4a2180f7a675399cdae295add0b07336575da7d05ebeeaeaadc` |
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
| Package suite | 8/8, 32.578 seconds | Fresh Core/Supervisor execution, not replayed receipts |
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
source. Neither defect was exercised on the owner installation.

## Changed-module coverage

Coverage combines ordinary tests with actual installed-helper/Core and App
process runs, using verified source-path mappings. App instrumentation is
laboratory-only. No changed production module is omitted.

| Module | Combined line/branch coverage |
|---|---:|
| Core entry/lifecycle | 89% |
| Core bridge | 92% |
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
identity headers are synthetic; they do not establish browser login or cookie
semantics. The real Core My component runs, but the external My relay/browser is
not visited by the offline campaign. All provider grants/accounts are synthetic.

Still required: actual Chrome native/status review in both languages and a
narrow viewport; clean exact-package review and remote checks; owner version and
encrypted-future-backup preflight; applicable exact-package installation/Core
restart approval; live dedicated Spotify consent through My, fresh native
confirmation, App restart, confirmed refresh/account match; owned retirement and
separately observed Spotify revocation. No real account, token, verifier, code,
private key, hostname or session route is included in this report.
