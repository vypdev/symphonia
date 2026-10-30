# Production OAuth readiness after the native trial

**Date:** 2026-10-30. **Outcome:** design remains Draft; no production implementation or deployment is approved by this review.
**Work:** [issue #38](https://github.com/vypdev/symphonia/issues/38).
**Baseline:** [PR #35](https://github.com/vypdev/symphonia/pull/35), merged into develop at `960168185ed22bf3b6a5a784bce113fdf1b2bff6`.

This is a manual application of the [existing SDD readiness questions](../../specs/README.md#8-acceptance-traceability-and-review), not another catalog, schema or publication gate. The owning contracts are the [companion](../../specs/home-assistant-oauth-companion.md), [authorization](../../specs/provider-connections-and-authorization.md) and [runtime](../../specs/home-assistant-app-runtime-and-ingress.md) SDDs. Their statuses remain Draft and their SDK-v1 inventory entries remain proposed.

## What is now established

The [dated trial report](native-oauth-trial-acceptance-2026-10-30.md#corrected-owner-campaign-at-852f3ea) records the exact corrected owner-tested `852f3ea` payload. Its twenty shipped source files and installer also match the evidence-only revision `dfcefc7` merged in PR #35. It is a separate twenty-minute, single-pair, single-profile App/helper, not an OAuth implementation inside the primary App.

The real owner matrix was Core 2026.10.4, Supervisor 2026.10.5, HAOS 18.3, Green/aarch64 and Chrome. Native pairing, new explicit Spotify `user-read-private` consent, S256 and the fixed My redirect, staged-only callback, a new initiating-administrator confirmation, App-owned encrypted grant, App restart and one confirmed refresh/account match passed. Native retirement, entry/App/helper removal, dedicated provider-grant revocation and post-restart absence checks passed. Both Core checks/restarts completed; the normal HA Spotify grant remained.

The separate package campaign passed 54 cases: 12 pure policy, 12 state, 12 adapter, 10 HTTP/UI and 8 integrated cases. Fault fixtures, installed-helper/Core observations, actual Supervisor/backup behavior, shipping-process evidence and real provider/browser results have distinct boundaries in the report. The controlled backup/restore and destructive actor tests ran in the laboratory, not on the owner's users or archives.

This establishes feasibility of the selected native route on that bounded matrix. It does not establish long-lived production pairing, renewal, key reset, concurrent grants, primary-App migrations, supported upgrades, an exact original browser/login session, library/copy access or playback. The operator callback-link observation incident is documented in the trial report; it is not a clean-output conformance pass for an entire future production release.

## Evidence against the sixteen production bridge cases

The labels below identify relevant trial observations, never completed production cases. Every L-case and its negative subcases still needs the production artifact's acceptance evidence.

| Production case | Relevant bounded observation | Remaining production acceptance |
|---|---|---|
| L01 pairing | Actual Supervisor alias, private CSR/mTLS and native owner pairing | Durable enrollment/renewal, revocation epochs and final artifact topology |
| L02 default My | Local HA settings initiated the default My flow | Full supported local/browser matrix and documented failure paths |
| L03 remote return | My returned to the selected existing HTTPS owner instance | Declared remote-browser/support profiles, not arbitrary network compatibility |
| L04 direct Core alternative | None from this trial | Exact trusted direct-Core HTTPS profile when My is disabled; remain gated |
| L05 same administrator | Fresh native confirmation preceded the real App exchange | Production adapter admission and immutable binding across all operations |
| L06 wrong actor | Synthetic actors denied by actual isolated Core HTTP | Full final-package actor/flow/pair negative matrix; no owner user changes |
| L07 logout/disable | Real Core fixture rejected revoked/disabled synthetic authority | Final supported-profile semantics; no continuous session-revocation claim |
| L08 state/redirect | Offline callback/decoder/policy fixtures | Production callbacks, duplicate/expired/hostile inputs and size/rate enforcement |
| L09 denial/cancel/expiry | Deterministic cases and isolated deadline/retirement execution | All production terminal states, cleanup and operator presentation |
| L10 per-flow PKCE | Per-attempt S256 and fixed public-client request observed | Concurrent authorizers and mismatch isolation in the final adapter |
| L11 lost acknowledgement/races | Durable trial fencing and controlled failure cases | Final connection/secret publication, multi-writer disconnect and orphan fences |
| L12 restart/unknown | Real App restart after activation; controlled process/restart tests | Core/App interruption at every production admission/publication phase |
| L13 identity/refresh | One real refresh matched the same account after App restart | Long-lived single-flight refresh, rotation and concurrent connection generations |
| L14 profiles/keys/versions | Trial wrong-pin/profile/key and retired-state checks | Production negotiation, renewal, unpair/version skew and no player authority |
| L15 backup/privacy | Actual isolated App key exclusion/locked restore; owner backup setting observed | Final package Core/App restore, migrations, key/reset/rotation and all output canaries |
| L16 cleanup | Real local retirement plus separate Spotify revocation; normal HA unaffected | Production remove versus unpair/disconnect, unreachable App and retained library/history |

## Ordered remaining work

| Order | Design or acceptance work | Owner and concrete exit evidence |
|---|---|---|
| 1 | Ratify the production protocol and supported artifact/profile contract | Companion + RFC: final envelope/error/size/rate bounds, version compatibility, public-client input, My/default and gated direct-Core alternative, declared HA/browser/architecture baseline |
| 2 | Specify durable enrollment and certificate renewal/revocation | Companion + key RFC: challenge/CSR/certificate transaction, current-key proof, renewal versus revoke/reset races, recoverable issuer result and no silent rebootstrap |
| 3 | Accept the lost-App-key recovery authority and UX | Companion/runtime + ADR 0008: current native admin proof plus protected App Origin/CSRF/signature binding, exact disclosed reset authority, interrupted reset/resume and absent/copied Core-key procedure; existing research is a candidate |
| 4 | Finalize grant publication, rotation and runtime concurrency | Authorization/runtime: exact repository/secret contracts, durable generations and leases, publication/disconnect/refresh/collector fences and orphan treatment; map the existing fault plan to actual process-death tests |
| 5 | Finish package/migration/backup/restore compatibility plans | Runtime: immutable artifact identities, source delivery and rollback, Core restore/re-pair, App-only locked restore, non-secret history preservation and supported upgrade/downgrade fixtures |
| 6 | Freeze provider capability and product scope | Authorization + RG-001: public Spotify read profile remains distinct from library/copy; explicit policy for any other provider/unofficial mode; no inference of API access from successful profile consent |
| 7 | Complete manual readiness review of the assembled contracts | Existing SDD standard: resolved design decisions, explicit remaining release tests, complete traceability, user states, numeric budgets, documentation, compatibility and standing owner authorization within its scope |
| 8 | Implement only the Ready increment, then execute its release gates | Final production package: deterministic suites, failure/restore/migration evidence and all applicable L01–L16 observations with scoped installation approval before a real owner run |

Design readiness requires a complete reviewable contract and necessary feasibility evidence. It is not a claim that unimplemented production tests already passed. The SDDs must resolve which decisions/prototypes are needed before implementation and which final-package tests belong to Definition of Done; this review does not waive or automatically move any existing mandatory gate. Unresolved protocol, recovery-authority, concurrency and compatibility decisions currently prevent readiness independently of the successful trial.

## Budgets and traceability remain unchanged

| Owning capability | Planned minimum | Main remaining traceability |
|---|---:|---|
| OAuth companion | 80 offline cases and 16 live bridge cases | SYM-HA-012, SYM-SEC-012/013/014/015; native actor/flow/pair/protocol and recovery |
| Provider authorization | 82 cases | SYM-ACC-002/004/006, SYM-PROV-002/003/019/022, SYM-SEC-003/007/013/014/015; grant ownership, account/capability identity, publication/refresh/disconnect |
| App runtime | 58 cases | SYM-HA-001/002/004/012, SYM-DEP-002/006/007/008/009, SYM-SEC-015; lifecycle, backup/restore, migration, locks and least privilege |

The existing category allocations and acceptance scenarios in the owning SDDs control. The trial's 54 cases, earlier research assertions and repository-wide test count are separate evidence; they cannot be subtracted from these minima or counted repeatedly for different capabilities. Pure policy remains deterministic and the existing 85% coverage floor is unchanged. UI-foundation and other capability budgets also remain in force.

## User/operator behavior carried forward

```text
Pair the reviewed App -> review the exact provider access -> native consent
-> callback waits -> the initiating administrator confirms -> App verifies
-> long-lived connection with App-owned refresh -> explicit recovery/disconnect
```

Native forms are host-owned. The primary App's connection, locked, action-required, uncertain and removal states still need the shared UI foundation, keyboard/focus, EN/ES, narrow/wide and declared browser evidence. A diagnostic trial screen or epoch timestamp is not the final production UX.

Keep the owner's accepted automatic-start local-key profile and encrypted Core-backup trust model. Core archives may retain its pairing identity after valid decryption; restore/cloning requires explicit App-side revoke/re-pair. App OAuth private keys remain excluded from ordinary backups; missing keys lock credentials and preserve non-secret data. Native current-admin approval, App Ingress authentication and exact original-login continuity are different claims. No grant reaches Core and no OAuth authority enables playback or a broad Core proxy.

The removed trial's grant, config entry or private keys are not migration inputs. Future production setup needs its own reviewed artifacts and fresh consent. Library import/copy, other provider profiles, direct-Core HTTPS support and stable release support are not enabled by this documentation. There is no new owner-HA operation in this increment.

## Manual review result

Evidence/current behavior and next-work ordering are now documented, with the old failed direct-callback experiment kept as historical evidence. Protocol/lifecycle/recovery decisions and complete production UX/configuration/compatibility contracts still need review. The three owning SDDs remain Draft; no Definition of Done checkbox or implementation claim is automatically promoted. The SDK validator/generator remains the controlling structural tool, and all changes use the installed Action-owned publication flow.
