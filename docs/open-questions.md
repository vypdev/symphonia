# Open questions, risks, and next design work

**Status:** open items and resolved decisions are marked individually
**Last reviewed:** 2026-10-25 (native OAuth companion and accepted automatic-start key/backup profile)

## Owner decisions and recorded outcomes

Open items are ordered roughly by how soon they block the next specification pass. Resolved items remain here for traceability.

### OQ-001 — What does “YouTube Music provider” mean for the MVP?

Official research currently proves a YouTube Data API for video playlists, not a full YouTube Music library/catalog API.

Existing Home Assistant projects prove that useful YouTube Music access is technically possible through reverse-engineered web endpoints, browser cookies, `ytmusicapi`, and proof-of-origin tokens. This reduces implementation-feasibility uncertainty but increases the evidence for authentication, account, policy, completeness, and maintenance risk; see the [ecosystem review](providers/home-assistant-ecosystem-review.md#youtube-music).

Options after the feasibility spike:

1. MVP supports official ordinary YouTube playlists and labels limitations clearly.
2. Defer the Google/YouTube side and choose another provider with an official music API.
3. Add a separately named unofficial YouTube Music adapter with explicit stability, authentication, terms, and account-risk warnings.
4. Accept a narrower hybrid, such as copying Spotify recordings to best-match YouTube videos without claiming library parity.

**Proposed default:** decide only after a test-account spike; never silently substitute reverse-engineered access.

### OQ-002 — Which playlist owns desired state after the copy MVP?

Choose provider-owned relationships (Option A), Symphonia-owned logical playlists (Option B), or the staged hybrid described in the [domain model](domain/domain-model.md#playlist-ownership-rfc-provider-owned-or-symphonia-owned).

**Proposed default:** staged hybrid—provider-owned copy first, retain enough origin/snapshot data to promote later. This is not accepted and persistent sync must not be designed until it is decided.

### OQ-003 — What is the default treatment of non-ready entries in a copy? — Resolved design

Options include:

- strict: no writes until every entry is resolved/supported;
- confirmed best effort: user explicitly accepts omissions;
- create target and pause at unresolved entries; or
- allow placeholders (only if a provider has a meaningful representation).

**Decision (2026-10-04, explicit owner response):** the initial copy policy is strict. Any `ambiguous`, `unmatched`, `unsupported`, `unavailable`, or `invalid` occurrence blocks acceptance and all target writes. There is no best-effort override in the initial release. The copy always creates a new target playlist, including when an existing playlist has the same name; matching names never select, append to, or overwrite a target. A later omission mode requires a separate product decision and contract update. Unknown create/add outcomes still require provider-aware reconciliation before retry; this decision does not settle rollback or cleanup after partial provider writes.

### OQ-004 — Which provider OAuth credentials and callback profile should self-hosters use?

Possibilities include project-owned shared client registrations, bring-your-own client credentials per install, or both. Spotify's five-user Development Mode cap strongly favors bring-your-own credentials for a distributed self-hosted project, but callback registration and support become harder.

**Direction updated (2026-10-25, explicit owner request):** prepare native
OAuth through a thin Symphonia auxiliary integration, without Cloudflare,
before implementation. [ADR 0007](decisions/0007-home-assistant-oauth-companion.md)
supersedes the earlier 2026-09-22 direct-App callback direction only for the HA
OAuth profile. The App still owns providers, durable grants/refresh and Ingress.
The default is BYO public Spotify client registration plus the fixed My redirect;
confidential-client and other-provider profiles remain separate decisions.

The [companion SDD](../specs/home-assistant-oauth-companion.md) and
[RFC](architecture/home-assistant-oauth-companion-rfc.md) propose staged code/PKCE
handoff, fresh native same-admin confirmation and private paired transport.
`RG-002`/`RG-008`, secret/key/backup and exact provider scope gates remain open.
The direction is accepted. The owner subsequently authorized continuing through
readiness, implementation and testing; the SDD readiness gate still applies.

### OQ-005 — What authentication/exposure does standalone mode use, and when does it ship?

Ingress supplies the primary App UI boundary. Standalone has no equivalent. Decide whether it ships in the MVP and choose local-only, reverse-proxy identity, built-in local credentials/passkeys, or another bounded mechanism. It must not bind an unauthenticated administrative UI broadly by default.

### OQ-006 — How many provider connections per type does the MVP UI support?

The domain supports multiple connections. The smallest UI could allow one Spotify and one Google connection while preserving connection IDs. Multiple family accounts improve usefulness but expand authorization, source/target selection, quota, and deletion UX.

### OQ-007 — What are the first-release size and hardware targets?

Provide representative numbers for saved recordings, playlists, largest playlist, provider connections, concurrent operations, target Home Assistant hardware, and acceptable import duration. These are needed before accepting database, pagination/cache, and measurable performance requirements.

### OQ-008 — What is the local-data/export policy?

Decide retention for immutable snapshots, operation detail, provider metadata, logs, rejected candidates, and deleted connections; whether the user can export/import mappings; and whether “forget all” is required in the MVP. Provider policy may impose stricter refresh/deletion behavior than product preference.

### OQ-009 — Which open-source license and contribution policy apply?

The repository currently has no license. The license should be selected before accepting outside contributions. Contributor handling of provider fixtures, terms, security reports, and trademarks also needs a policy.

### OQ-010 — How should cancellation recover after a worker loses an uncertain external write? — Resolved design

**Decision (2026-09-26, selected under owner delegation):** use `waiting_user` as the provider-independent safety boundary. If a cancellation-requested worker lease expires, quarantine the operation with a durable reconciliation marker; never dispatch its ordinary handler again and never report it as cancelled while the external outcome is unknown. An authorized operator must establish `no_effect` (terminal `cancelled`) or `effect_confirmed` (terminal `partial`) before clearing the cancellation request. If neither fact can be established, it stays in `waiting_user`.

This foundation deliberately does not guess at provider reconciliation or expose an unauthenticated resolution endpoint. A future provider-aware reconciliation handler may resolve the outcome automatically only after its provider contract is proven. The repository primitive for explicit resolution is not itself an authorization boundary; any caller must enforce the approved operator identity and action policy. The durable-operation SDD remains blocked on that provider/UI vertical and its other readiness gates, but OQ-010 no longer represents an unresolved policy choice.

### OQ-011 — Which complete playback profiles can be promised?

The owner wants a Home Assistant-integrated listening surface alongside playlist management; see the [listening SDD](../specs/listening-and-playback-control.md). **Authority boundary resolved (2026-09-28):** the owner chose a narrow companion playback broker, recorded in [ADR 0006](decisions/0006-narrow-home-assistant-playback-broker.md), instead of granting the App broad Supervisor Core API authority. **Scope direction (2026-09-28):** the owner rejected an active-session-only Spotify first release and requested the complete listening experience across the desired connected providers, including starting media, choosing where it plays, current playback, transport controls, and changing playlists. Internal implementation increments are allowed, but an active-session-only prototype is not a complete-release claim. The supported source/output matrix and broker transport, pairing, versioning, user attribution, and threat model remain open. This is independent of `OQ-004`'s provider OAuth callback decision: provider import credentials do not authorize HA player control.

**Unresolved feasibility and authority:** the [source review](providers/playback-integration-source-review.md) shows that stock HA Spotify drops `PLAY_MEDIA` while idle and selects devices by name, so it alone cannot substantiate the requested idle-start/exact-output experience. A separate, explicitly consented Spotify Connect adapter with its own read/control scopes is a possible complement, **not** an accepted fallback; it requires owner approval, a separate threat/policy review, account binding and live proof. Music Assistant players and its unofficial YouTube Music source need independent account/caller/queue and support-risk review. `ytube_music_player` is optional community evidence, not an automatic dependency. Native YouTube Music app sessions are not proven observable. Multiple active players are selected explicitly. There is no fallback to a generic Core API relay. The [full-scope proof plan](development/playback-release-gates.md) makes the release claims and required evidence explicit. The [broker protocol RFC](architecture/playback-broker-protocol-rfc.md) proposes a reverse authenticated channel but is **not accepted** until topology, pairing, secret/backup and caller-identity proof closes its gates.

### OQ-012 — Automatic-start OAuth key and backup trust — Resolved direction

**Decision (2026-10-25, explicit owner answers):** automatic startup with protected
install-local keys, then the HA trust model with encrypted Core backups.
[ADR 0008](decisions/0008-install-local-oauth-keys-and-backups.md) records separate
private Core pairing files, encrypted HA identity archives and excluded App
OAuth keys. Core restore requires operator App-pair revocation/re-pair; copied
identity detection is not promised. Missing App keys require authenticated
reset/new consent while preserving non-secret history. The choice is closed;
final package, reset/rotation/publication and live conformance remain research
gates. Standalone and playback key profiles are not approved by this decision.

## Research/design gates (not owner preference alone)

### RG-001 — Official provider feasibility

Run the dated Spotify and YouTube test-account matrix in [provider research](providers/provider-research.md). Record scopes, account tier, app mode, market, exact endpoints, quota cost, payload gaps, playlist visibility, duplicate/order behavior, and cleanup results. Do not use personal libraries as fixtures.

The official documentation was revalidated on 2026-09-22. That refresh confirms
the documented Spotify playlist write limits and authorization lifetime, and
that the public YouTube Data API remains a video-playlist surface rather than
proof of full YouTube Music library parity. A dedicated test-account run is
still required before this gate can close.

If Apple Music is considered as a future provider or fallback for an official music-library surface, run its separate feasibility gates without silently changing the MVP. Community providers may inform test cases but cannot substitute for official-contract evidence.

### RG-002 — Provider OAuth for the Home Assistant App

Validate the ADR 0007 native companion/Core callback route, with App-owned
exchange/refresh and the paired protocol from `RG-008`. First prove the minimal
Spotify PKCE profile; Google needs its own accepted registration/secret/scopes.
Test:

- local and externally reachable Home Assistant URLs;
- HTTPS and exact registered redirects;
- named native-flow/current-admin/pair identity, multiple users and honest session/revocation limits;
- OAuth `state`, PKCE where applicable, single use, expiry, denial, and restart;
- user-provided OAuth client registrations; and
- token ownership, refresh, revocation, App/integration version skew, and backup/restore;
- no public App callback or tunnel, and no internal OAuth channel access to management/playback routes; and
- no secrets in App options, browser-export files, URL query logs, referrers, or diagnostics.

The result is conformance evidence for the Draft authentication/secret-storage
contracts, not permission for production code. Earlier [direct callback](development/oauth-callback-spike.md)
and [owner trial](development/ha-oauth-trial-2026-10-25.md) results remain dated
research; they do not close the new companion topology/identity gates.

### RG-003 — Matching evidence corpus

Build and review a licensed/synthetic labeled corpus containing exact duplicates, missing/wrong ISRC, covers, live/studio, remasters, remixes/edits, clean/explicit, acoustic, compilations, featured artists, localized metadata, music/lyric videos, and misleading titles. Use it to specify confidence rules and measurable false-link tolerances.

### RG-004 — Durable operation and storage spike

Compare SQLite and PostgreSQL for transaction boundaries, leases, crash recovery, unknown writes, snapshot/history queries, online/cold backup under Supervisor, encryption-key restore, representative library size, and a per-migration applied ledger across stable/beta upgrade paths. Prove that a failed migration never replaces irrecoverable manual decisions/audit state with a fresh rescan. No framework selection should precede these results.

The current local evidence includes a [reproducible SQLite recovery and backup
spike](development/storage-recovery-spike.md) covering an expired lease across
runtime restart and read-only backup validation, with separate phase timings
and the SQLite runtime version. Its synthetic per-operation payload size is
configurable for sensitivity runs, but is not representative data. It is an
initial evidence point, not a storage choice, representative-scale conclusion,
or production SLO.

### RG-005 — Home Assistant native surface RFC

Define what belongs in the App UI versus a companion custom integration. Decide transport/auth/version discovery and a minimal entity/action/event surface. Ensure Home Assistant actions create ordinary audited Symphonia operations and that the integration can be unavailable independently.

The OAuth part is now specified by ADR 0007 and the companion SDD; generic
native entities/actions/events remain deferred. OAuth and playback profiles
must not expand one another's authority.

### RG-006 — Home Assistant UI compatibility and host-context spike

The owner has accepted the Home Assistant-native-adjacent direction, independent compatibility layer, and no-private-frontend-dependency boundary in [ADR 0004](decisions/0004-home-assistant-native-ui.md), and selected Lit + TypeScript + Vite in [ADR 0005](decisions/0005-lit-typescript-vite-ui.md). [Current official-source research](development/ui-spike/host-context-evidence.md) finds no theme/locale/timezone fields in the inspected App-properties message. Before the [UI foundation SDD](../specs/home-assistant-native-ui.md) becomes `Ready for implementation`, a documentation/prototype spike must:

- declare the supported Home Assistant and evergreen-browser matrix;
- verify arbitrary Ingress base paths, deep links, refresh, assets, HTTP, and any WebSocket/SSE transport;
- capture the exact supported public contract for theme, locale, direction, timezone, safe-area insets, and context changes, including origin/message/schema validation and deterministic fallback;
- verify the selected Lit/Vite approach against component-package isolation, bundle/old-device cost, accessibility, localization, catalog, and standalone reuse;
- create a dated official Home Assistant reference manifest with public-data provenance, light/dark availability, phone/wide viewports, human review ownership, and immutable history;
- prototype representative navigation, card, button, form, status/alert, dialog, progress/empty, settings/list row, dense data, and ordered-evidence components without production feature behavior; and
- prove keyboard/focus/announcement, reduced-motion, contrast, long/RTL text, safe-area/zoom/virtual-keyboard, no document overflow, and bounded table/diagnostic scrolling.

The tooling choice is accepted; the result must still establish a supported matrix and validated host/visual contracts. It does not authorize production UI work until the SDD is ready and the owner explicitly approves implementation.

### RG-007 — Listening source, target, and command feasibility

Use a disposable Home Assistant installation and dedicated accounts/devices after the broker protocol/security decision. Record the exact versions and account identities for HA Spotify, Music Assistant, and any proposed community player. Run the [dated source-review proof matrix](providers/playback-integration-source-review.md#rg-007-proof-matrix-before-release) and the [complete-release plan](development/playback-release-gates.md): verify Spotify idle/active/restricted and duplicate-name device behavior, WebSocket versus service browsing and service feature gates, exact-output/start feasibility, MA queue versus external source and per-user/default-user attribution through the **actual companion-broker route**, playlist reference mapping, private/unavailable/large playlist behavior, state-update/device-discovery lag, accepted-but-unobserved commands, external-controller races, HA restart, and credential recovery. If a separate Spotify Connect path is approved, also prove current endpoint access, fresh device IDs, separate read/control grants, account identity, idle-start/output confirmation and revocation without reusing the HA broker credential. Prove whether account identity can be machine-verified; if not, specify a visible user-confirmed but unverified binding and forbid automatic private-playlist mapping. Test hostile entity/media IDs, MA free-text/URL/path fallback rejection, broker pairing/version/replay/secret isolation, and ensure no broker credential reaches Ingress/browser state. Decide freshness/command-confirmation budgets from these observations. Keep community implementation findings separate from official platform evidence and do not infer control of native YouTube Music app sessions.

A [disposable Core/MA Compose lab](development/playback-lab/README.md) is now prepared and its Compose configuration validates locally. It has not been started or used with test accounts/devices; it provides no live pass. Because Home Assistant Container lacks Supervisor/Apps/Ingress, a separate HAOS/Supervisor-compatible environment is still required for broker topology and App authentication proof.

### RG-008 — Native OAuth companion conformance

**Bounded evidence (2026-10-25):** [the lab run](development/ha-oauth-companion-lab-2026-10-25.md)
now demonstrates native main-flow/request-actor feasibility, an actual paired
TLS route and App exclusion/locked-restore behavior. It also confirms that
private HA storage and unprotected backups can contain plaintext controls.
ADR 0008 now selects install-local key custody and distinct encrypted-Core/
excluded-App backup rules. [Follow-up research](development/local-key-custody-lab-2026-10-25.md)
proves local key reopen in a second container, private Core identity reopen in a
new process and actual protected Core archives. Final adapters/package, CSR,
reset/rotation/publication and supported-version/browser/provider acceptance
remain open. Core restore itself and cloned-identity detection were not tested.

Before [the companion SDD](../specs/home-assistant-oauth-companion.md) can leave
Draft, prove the [RFC](architecture/home-assistant-oauth-companion-rfc.md) in a
disposable HA installation with dedicated public client registration:

1. Complete supported-version/browser/package conformance of the now-exercised native config-flow extension points, fresh current administrator
   at begin/confirm, exact flow binding, per-attempt PKCE, staged-only callback
   and no default token-bearing config entry/HA refresh owner.
2. Production provisioning/renewal beyond the proven Supervisor-internal alias and pinned mutual TLS route, temporary pairing,
   key protection, epoch revocation, strict OAuth-only schemas and version skew;
   no host mapping, broad Core credential or authority inherited by playback.
3. App-only exchange/secret publication, lost acknowledgement, crash/disconnect
   fencing, uncertain outcomes, sealed-orphan cleanup and single-flight refresh.
4. HA/App key and backup/restore contracts with credential canaries; config-entry
   encryption must not be assumed. Re-pair after restore and truthful offline removal.
5. The 16 live cases, local/remote browser paths, supported direct-Core HTTPS
   alternative and exact HA/App/integration/browser matrix. A documentation
   example or the previous direct tunnel trial is not a bridge pass.

The owner authorized continuation through readiness and subsequent implementation/
testing. This does not make a Draft SDD ready or claim an owner-instance pass.
The planned 80-case offline budget does not replace the authorization/runtime
budgets or the 16-case release matrix.

## Future synchronization questions

These do not block the copy MVP but block sync implementation:

- Which modes ship first: mirror, add-only, or bidirectional?
- Does order matter in every mode and how are duplicate occurrences identified?
- What baseline identifies “changed on both sides” when a provider lacks a reliable revision token?
- Are target-side additions preserved, propagated, or conflicts in mirror mode?
- How are removals, playlist deletion, privacy change, renames, and unavailable tracks handled?
- What happens when a previously resolved provider item becomes unavailable or changes metadata materially?
- How are loops prevented when Symphonia observes its own delayed provider writes?
- What schedule, jitter, quiet hours, manual trigger, and Home Assistant automation behavior are expected?
- How long can a relationship be degraded before the UI requires intervention?

## Implementation decisions intentionally deferred

- backend language and framework;
- supported HA/browser matrix and Lit/Vite compatibility evidence; the UI stack is accepted by ADR 0005 and the design-system contract by ADR 0004;
- SQLite versus PostgreSQL;
- internal durable runner versus job library;
- final secret encryption library/package and reset/rotation/publication contract; the HA automatic-start local-key trust direction is accepted in ADR 0008;
- API/event protocol and versioning;
- companion integration transport;
- App CPU architectures and supported Home Assistant versions;
- release channels and version/support policy;
- exact matching scores/thresholds; and
- telemetry exporters (if any; no external telemetry by default is implied for self-hosting).

These need evidence and small RFCs; popularity is not evidence.

## Risk register

| Risk / assumption | Likelihood | Impact | Current response |
| --- | --- | --- | --- |
| Official YouTube API does not provide the intended YouTube Music model | High | Critical: symmetric MVP promise fails | `RG-001`, then owner choice `OQ-001` |
| Unofficial YouTube Music access requires reusable browser-account cookies and moving private endpoints | High | Critical security/account/support risk | Separate opt-in adapter only; threat model; no silent fallback; `OQ-001` |
| Native OAuth flow/paired actor and code handoff cannot meet the security contract | Medium-high | Critical: users cannot connect providers safely | ADR 0007, `RG-002`/`RG-008`; no public App callback fallback |
| A direct callback port accidentally exposes the management API outside Ingress | Medium | Critical compromise risk | Callback-only listener, independent auth, non-root/least privilege, App artifact tests |
| Spotify Development Mode endpoints/policy change again or required endpoint is restricted | Medium-high | High | Capability probes, dated matrix, graceful disable, avoid hosted assumptions |
| Spotify six-month refresh-token lifetime creates unexpected reconnect failures | High under current docs | Medium-high | Expiry tracking, warnings, `waiting_user`, easy reauthorization |
| Google quota/search budget makes track-by-track matching impractical | High for naive search | High | Batch/cache within policy, plan quota, corpus, bounded candidate strategies |
| YouTube 30-day refresh/deletion policy conflicts with durable local identity/history | Medium | High | Separate provider payloads from user decisions; retention RFC |
| ISRC/similar metadata produces false links across versions | High | High | Conservative rules, evidence, review queue, negative/manual mappings |
| Provider write timeout creates duplicate playlist entries on retry | Medium | High | Checkpoints, stable keys, target reconciliation, unknown-outcome state |
| Provider-owned versus logical playlist choice is delayed until sync code | Medium | High architectural rework | Decide before sync; keep copy/snapshots model-neutral |
| App backups contain usable provider tokens or lose the decryption key | Medium | Critical security/recovery failure | Threat model, external key design, restore tests, sanitized export |
| Single-node embedded storage cannot handle job concurrency/backup safely | Low-medium | Medium | `RG-004`; no multi-replica claim |
| Home Assistant coupling leaks into domain/application | Medium | High maintenance/portability cost | ADR 0003 dependency rule and architecture tests |
| Native-looking UI depends on unstable private Home Assistant components or drifts into an unrelated SaaS design | Medium | High compatibility and product-coherence cost | ADR 0004, owned compatibility layer, `RG-006`, dated official references, catalog/a11y/responsive/visual release gates |
| Listening UI confuses library account, HA source, and speaker or shows accepted commands as confirmed playback | High without explicit contract | High: wrong output/account and misleading controls | `OQ-011`, `RG-007`, explicit binding, exact references, observed-effect reconciliation |
| Broker pairing/operation scope fails or unofficial YT Music credentials cross into browser/diagnostics | Medium | Critical privacy/control risk | ADR 0006 narrow broker, pairing/replay/secret threat review, entity/action allowlist, no cookie handoff |
| Unknown target library sizes lead to unjustified performance design | High | Medium | `OQ-007`, measurable targets before optimization |
| Future Apple Music support is mistaken for full sync despite no documented remove/reorder operation | Medium | High if scope is promoted | Per-operation/object capability probes; Apple feasibility gates before scope change |

## Recommended next five specification/design tasks

1. **Provider feasibility report (`RG-001`).** Prove or narrow the Spotify ↔ YouTube promise using official APIs and dedicated accounts; feed the evidence into the provider, [import](../specs/library-import-and-provider-projections.md), and [copy](../specs/one-time-playlist-copy.md) SDDs. Report unofficial YT Music evidence separately and keep Apple as an explicit future/contingency spike.
2. **Close the [authorization](../specs/provider-connections-and-authorization.md) and [OAuth companion](../specs/home-assistant-oauth-companion.md) blockers (`RG-002`/`RG-008` + `OQ-004`).** Prove the native Core/My flow, private pairing/current actor, App-only grants, BYO profiles, encryption, revocation and backup/restore.
3. **Close the remaining [copy SDD](../specs/one-time-playlist-copy.md) feasibility blockers.** The strict/create-new policy is accepted; prove target create/add/order/duplicate behavior with dedicated accounts, provider-specific name/visibility validation, unknown-write reconciliation, and partial-failure recovery before implementation readiness.
4. **Close the [identity SDD](../specs/recording-identity-resolution.md) evidence blockers (`RG-003`).** Build the corpus and settle normalization, candidate sources, evidence, versioned rules, manual decisions, and measurable safety targets.
5. **Define the [listening](../specs/listening-and-playback-control.md) vertical (`OQ-011`/`RG-007`) alongside [runtime](../specs/home-assistant-app-runtime-and-ingress.md) and [durable-operation](../specs/durable-operations-and-recovery.md) blockers (`RG-004`).** Specify and threat-review the selected companion-broker protocol and prove source/account/player/output behavior before promising Spotify or YouTube Music controls; choose process topology/storage only after crash, lease, migration, backup, and representative-scale evidence.

After those tasks, revisit playlist ownership (`OQ-002`) before creating any
persistent-synchronization SDD. Generic native projections (`RG-005`) remain
independent; the selected OAuth auxiliary setup is required for new HA provider
consent, not for continued use of already verified App grants.

The UI compatibility spike (`RG-006`) can also proceed in parallel as non-production evidence. It must prove the supported host/browser/context matrix and selected Lit/Vite tooling before the broader UI foundation or feature views are implemented; the separately approved read-only operational dashboard is already available, while feature content and behavior remain owned by their SDDs.
