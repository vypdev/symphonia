# Open questions, risks, and next design work

**Status:** open; nothing here is an accepted decision
**Last reviewed:** 2026-09-26

## Decisions requiring owner input

These are ordered by how soon they block the next specification pass.

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

### OQ-003 — What is the default treatment of non-ready entries in a copy?

Options include:

- strict: no writes until every entry is resolved/supported;
- confirmed best effort: user explicitly accepts omissions;
- create target and pause at unresolved entries; or
- allow placeholders (only if a provider has a meaningful representation).

**Proposed default:** strict by default with an explicit, itemized best-effort override. Rollback/cleanup after partial provider writes still needs design.

### OQ-004 — Which provider OAuth credentials and callback profile should self-hosters use?

Possibilities include project-owned shared client registrations, bring-your-own client credentials per install, or both. Spotify's five-user Development Mode cap strongly favors bring-your-own credentials for a distributed self-hosted project, but callback registration and support become harder.

Owner direction (2026-09-22): follow the `vypdev/homeassistant-gateway`
deployment pattern. The Supervisor App owns the provider adapters and the
Ingress UI/API; a companion integration is not required to broker OAuth for
the MVP. The working authorization shape is therefore a direct App-owned,
callback-only flow. `RG-002` still has to prove callback reachability, exact
redirect registration, state/PKCE/single-use behavior, secret ownership, and
local/remote Home Assistant operation before the implementation contract is
ready.

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

### OQ-010 — How should cancellation recover after a worker loses an uncertain external write?

If cancellation is requested while a provider write is in flight and the worker disappears before recording the response, the system cannot safely assume the write did not happen. Choose between a durable reconciliation-required phase that resumes only reconciliation, or a `waiting_user` state that blocks until an explicit manual action. The operation must not be reported as fully cancelled while the external outcome remains unknown.

**Proposed default:** persist the in-flight step and reconcile it before finalizing cancellation; use `waiting_user` if the provider cannot safely confirm the outcome. The current operation state model does not yet define this recovery transition.

## Research/design gates (not owner preference alone)

### RG-001 — Official provider feasibility

Run the dated Spotify and YouTube test-account matrix in [provider research](providers/provider-research.md). Record scopes, account tier, app mode, market, exact endpoints, quota cost, payload gaps, playlist visibility, duplicate/order behavior, and cleanup results. Do not use personal libraries as fixtures.

The official documentation was revalidated on 2026-09-22. That refresh confirms
the documented Spotify playlist write limits and authorization lifetime, and
that the public YouTube Data API remains a video-playlist surface rather than
proof of full YouTube Music library parity. A dedicated test-account run is
still required before this gate can close.

If Apple Music is considered as a future provider or fallback for an official music-library surface, run its separate feasibility gates without silently changing the MVP. Community providers may inform test cases but cannot substitute for official-contract evidence.

### RG-002 — OAuth through a Home Assistant App

Prototype authorization start/callback/error for Spotify and Google using a direct App-owned, callback-only flow. Test:

- local and externally reachable Home Assistant URLs;
- HTTPS and exact registered redirects;
- Ingress base path/session and multiple browser users;
- OAuth `state`, PKCE where applicable, single use, expiry, denial, and restart;
- user-provided OAuth client registrations; and
- token ownership, refresh, revocation, App/integration version skew, and backup/restore;
- a callback-only direct listener that does not expose management routes; and
- no secrets in App options, browser-export files, URL query logs, referrers, or diagnostics.

The result becomes an authentication/secret-storage RFC, not production code.
The current local evidence is recorded in the [direct App OAuth callback
spike](development/oauth-callback-spike.md); it proves route isolation and
durable single-use state but does not close the Home Assistant topology gate.

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

### RG-006 — Home Assistant UI compatibility and host-context spike

The owner has accepted the Home Assistant-native-adjacent direction, independent compatibility layer, and no-private-frontend-dependency boundary in [ADR 0004](decisions/0004-home-assistant-native-ui.md). Before the [UI foundation SDD](../specs/home-assistant-native-ui.md) becomes `Ready for implementation`, a documentation/prototype spike must:

- declare the supported Home Assistant and evergreen-browser matrix;
- verify arbitrary Ingress base paths, deep links, refresh, assets, HTTP, and any WebSocket/SSE transport;
- capture the exact supported public contract for theme, locale, direction, timezone, safe-area insets, and context changes, including origin/message/schema validation and deterministic fallback;
- compare candidate frontend/build approaches against component-package isolation, bundle/old-device cost, accessibility, localization, catalog, and standalone reuse;
- create a dated official Home Assistant reference manifest with public-data provenance, light/dark availability, phone/wide viewports, human review ownership, and immutable history;
- prototype representative navigation, card, button, form, status/alert, dialog, progress/empty, settings/list row, dense data, and ordered-evidence components without production feature behavior; and
- prove keyboard/focus/announcement, reduced-motion, contrast, long/RTL text, safe-area/zoom/virtual-keyboard, no document overflow, and bounded table/diagnostic scrolling.

The result selects the presentation implementation/tooling and supported matrix. It does not authorize production UI work until the SDD is ready and the owner explicitly approves implementation.

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
- UI framework/build tooling and supported HA/browser matrix; the Home Assistant-native design-system contract itself is accepted by ADR 0004;
- SQLite versus PostgreSQL;
- internal durable runner versus job library;
- secret encryption primitive and key source;
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
| OAuth callback cannot be made reliable/simple through Ingress for bring-your-own clients | Medium-high | Critical: users cannot connect providers safely | `RG-002`; keep callback design open |
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
| Unknown target library sizes lead to unjustified performance design | High | Medium | `OQ-007`, measurable targets before optimization |
| Future Apple Music support is mistaken for full sync despite no documented remove/reorder operation | Medium | High if scope is promoted | Per-operation/object capability probes; Apple feasibility gates before scope change |

## Recommended next five specification/design tasks

1. **Provider feasibility report (`RG-001`).** Prove or narrow the Spotify ↔ YouTube promise using official APIs and dedicated accounts; feed the evidence into the provider, [import](../specs/library-import-and-provider-projections.md), and [copy](../specs/one-time-playlist-copy.md) SDDs. Report unofficial YT Music evidence separately and keep Apple as an explicit future/contingency spike.
2. **Close the [authorization SDD](../specs/provider-connections-and-authorization.md) blockers (`RG-002` + `OQ-004`).** Validate the direct App callback flow, then settle bring-your-own credentials, encryption, revocation, and backups.
3. **Close the [copy SDD](../specs/one-time-playlist-copy.md) policy blocker (`OQ-003`).** Decide target creation, strict/best-effort behavior, batching, partial failure, reconciliation, cancellation, and exact acceptance examples.
4. **Close the [identity SDD](../specs/recording-identity-resolution.md) evidence blockers (`RG-003`).** Build the corpus and settle normalization, candidate sources, evidence, versioned rules, manual decisions, and measurable safety targets.
5. **Close the [runtime](../specs/home-assistant-app-runtime-and-ingress.md) and [durable-operation](../specs/durable-operations-and-recovery.md) SDD blockers (`RG-004`).** Choose process topology and storage only after crash, lease, migration, backup, and representative-scale evidence.

After those tasks, revisit playlist ownership (`OQ-002`) before creating any persistent-synchronization SDD. The Home Assistant native surface (`RG-005`) can proceed in parallel once the service API shape is stable, but it is not a prerequisite for the copy MVP.

The UI compatibility spike (`RG-006`) can also proceed in parallel as non-production evidence. It must settle the supported host/browser/context/tooling matrix before any production frontend work, while feature content and behavior continue to be owned by their existing SDDs.
