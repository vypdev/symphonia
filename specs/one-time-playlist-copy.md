# One-time playlist copy

- Status: Draft
- Date: 2026-09-20
- Catalog capability ID: `one-time-playlist-copy`
- Owners: Symphonia maintainers
- Scope: preview and execute a finite playlist copy using an immutable plan, explicit non-ready policy, ordered writes, reconciliation, and item-level outcomes.
- Related requirements: `SYM-PROD-002`, `SYM-PROD-004`–`SYM-PROD-006`, `SYM-PL-001`–`SYM-PL-009`, `SYM-PROV-010`, `SYM-PROV-019`, `SYM-ARCH-009`–`SYM-ARCH-010`, `SYM-JOB-003`–`SYM-JOB-005`, `SYM-TEST-004`, `SYM-TEST-006`
- Related decisions/research: [ADR 0002](../docs/decisions/0002-copy-and-sync-are-distinct.md), [copy domain model](../docs/domain/domain-model.md), [provider research](../docs/providers/provider-research.md), `OQ-003`, `RG-001`
- Required review gates: product UX, domain, architecture, provider feasibility, testing, documentation, security/operations
- Open decisions blocking readiness: default non-ready policy; proven target write behavior; target collision policy; reconciliation semantics for ambiguous provider writes

## 1. Executive summary

Symphonia shall copy one imported playlist to another provider as a finite, reviewable operation. Before any target mutation, it shall capture an immutable source snapshot, resolve provider identities, build a dry-run plan, disclose every non-ready or deliberately omitted item, and require explicit acceptance of that exact plan.

The operation is intentionally not persistent synchronization. A later source change does not mutate the accepted plan or trigger another copy. Retrying an operation shall be idempotent and shall reconcile uncertain provider outcomes before issuing another write.

## 2. Problem statement and evidence

Users need to move a playlist without trusting an opaque best-effort process that may silently substitute tracks, reorder entries, lose duplicates, or create multiple target playlists after a restart.

The horizontal product and provider specifications require dry runs, durable background work, explicit ambiguity, provider capability checks, and a distinction between canonical recording identity and provider-specific availability.

Evidence sources:

- [Product specification](../docs/product/product-specification.md)
- [Domain model](../docs/domain/domain-model.md)
- [Provider specification](../docs/providers/provider-specification.md)
- [System architecture](../docs/architecture/system-architecture.md)
- [Open questions](../docs/open-questions.md)

## 3. Actors and authorization

- A Home Assistant administrator configures provider connections and service-level limits.
- An authorized household user selects the source playlist, target provider, and allowed resolution decisions.
- Symphonia plans and executes the copy using only connections that the requesting user is authorized to use.
- Provider adapters expose target capabilities and perform provider-specific reads and writes.

The exact Home Assistant identity-to-Symphonia-user mapping remains an architectural decision. Until it is resolved, implementations shall not assume that every Ingress visitor may use every stored provider credential.

## 4. Goals, non-goals, and invariants

### Goals

- Produce a complete, stable dry-run plan before target mutation.
- Preserve source entry order and duplicate occurrences when supported.
- Distinguish ready, ambiguous, unmatched, unsupported, unavailable, and invalid entries while retaining resolution evidence and any deliberate omission separately.
- Execute the accepted plan durably and idempotently.
- Make partial success and recovery actions understandable.

### Non-goals

- Continuous or bidirectional synchronization.
- Silent fuzzy matching or automatic acceptance below a documented confidence threshold.
- Editing the source playlist.
- Updating an existing target playlist unless a future decision explicitly defines collision and ownership semantics.
- Guaranteeing that every source item exists on the target provider.

### Invariants

- No provider write occurs before the user accepts the exact plan digest.
- A plan is immutable after acceptance; changes produce a new plan.
- Every source occurrence has a terminal plan classification.
- Unresolved and ambiguous entries are never silently substituted.
- Unknown provider write outcomes are reconciled before retry.
- Cancellation stops future work but does not claim to undo confirmed provider writes.
- Audit data can relate every target write to the accepted plan and source snapshot.

## 5. User journey and primary flow

1. The user selects an imported source playlist and a connected target provider.
2. Symphonia captures the source projection version, entry order, provider capabilities, connection identity, and relevant resolution decisions.
3. Symphonia resolves every source occurrence to a target provider item or a disclosed non-ready classification.
4. Symphonia creates an immutable plan and calculates its digest.
5. The user reviews counts, target settings, ambiguities, unavailable items, and policy consequences.
6. The user resolves eligible ambiguities or excludes items explicitly. Each change creates a revised plan and digest.
7. The user accepts the final plan.
8. A durable operation creates the target playlist, adds entries in planned order, checkpoints progress, and reconciles uncertain results.
9. Symphonia presents a per-item result and an operation summary.

If the source projection or relevant provider capability changes before acceptance, the plan becomes stale and must be regenerated. Changes after acceptance do not alter the operation.

## 6. Functional contract and state model

### Plan entry classifications

Each source occurrence has exactly one classification required by `SYM-PL-003`:

- `ready`: one target item is approved for writing; its resolution basis records whether it came from strong automatic evidence or a user decision.
- `ambiguous`: multiple plausible candidates require a decision.
- `unmatched`: no sufficiently supported candidate exists.
- `unsupported`: the provider cannot represent or add the item type.
- `unavailable`: the canonical recording is known but not playable/addable on the target.
- `invalid`: the source occurrence cannot participate because its imported representation is malformed or violates an invariant.

Classifications apply per occurrence, not just per recording, so duplicates remain visible and ordered. A separate disposition records whether a non-ready occurrence is blocked or deliberately omitted under the accepted policy; omission does not erase or rename its classification.

### Plan states

- `draft`: still being calculated or edited.
- `ready_for_review`: calculation is complete and internally consistent.
- `blocked`: the selected policy and one or more non-ready entries prevent acceptance.
- `accepted`: the user accepted the exact digest.
- `stale`: pre-acceptance evidence or capabilities changed.
- `superseded`: another revision replaced this plan.

### Operation states

The operation uses the durable job vocabulary defined by `durable-operations-and-recovery`: `queued`, `running`, `waiting_rate_limit`, `waiting_user`, `retry_scheduled`, `succeeded`, `partial`, `failed`, or `cancelled`.

### Proposed initial acceptance policy

Until OQ-003 is decided, the proposed default is strict: a plan cannot be accepted while any occurrence is not `ready`. A future explicit best-effort policy may permit itemized omission of `ambiguous`, `unmatched`, `unavailable`, `unsupported`, or `invalid` occurrences after prominent disclosure. This proposal is not final product policy.

### Target creation and collision policy

The safe initial behavior is create-only with a provider-visible operation marker when the provider permits it. Symphonia shall not overwrite, clear, or append to a pre-existing playlist solely because its name matches. The final collision policy is a readiness blocker.

## 7. Configuration contract

| Setting | Scope | Default | Validation and notes |
|---|---|---|---|
| Target playlist name | Per plan | Source name | Must satisfy target provider rules; normalized value shown before acceptance. |
| Target visibility | Per plan | Private where supported | Available values come from provider capabilities. |
| Non-ready entry policy | Product policy | Strict, proposed | Final policy blocked by OQ-003. |
| Existing target behavior | Product policy | Create only, proposed | No implicit overwrite or append. |
| Batch size | Adapter/runtime | Provider-specific | Bounded by provider limits; not exposed as an arbitrary user tuning knob initially. |
| Retry policy | Adapter/runtime | Conservative | Must distinguish safe retry from unknown outcome. |

Dry-run review, audit creation, plan digest validation, and reconciliation cannot be disabled.

## 8. Architecture and boundaries

### Domain layer

Owns source snapshots, plan revisions, entry classifications, target intent, accepted digests, and copy outcomes. It contains no Home Assistant or provider SDK types.

### Application layer

Coordinates snapshot capture, identity lookup, plan calculation, acceptance, operation dispatch, checkpointing, and reconciliation.

### Ports

- Read a stable imported playlist projection.
- Query provider capabilities and connection authorization.
- Resolve a canonical recording to target candidates.
- Create and inspect a target playlist.
- Add ordered batches and reconcile their outcome.
- Persist plans, results, checkpoints, and audit events.

### Adapters

- Provider adapters implement capability discovery and writes.
- Persistence adapters store immutable plan revisions and operation state.
- The Home Assistant-facing adapter exposes the web UI and, later, narrowly scoped services if approved.

Provider-specific workarounds shall remain behind ports and shall not alter domain invariants.

## 9. UI, UX, and accessibility

The review page shall show:

- source playlist and captured version;
- target account, provider, normalized name, and visibility;
- total occurrences and counts for every classification;
- ordered entry details with evidence and alternative candidates;
- consequences of omitting non-ready entries under the selected policy;
- the fact that this is a one-time snapshot, not synchronization;
- the accepted plan digest in an advanced details view.

Example summary:

> 124 source entries: 116 ready, 2 ambiguous, 4 unavailable on the target, and 2 unsupported. Nothing has been written yet.

Example blocked action:

> Review 2 ambiguous entries before this strict plan can be accepted.

Example partial result:

> The target playlist was created with 113 confirmed entries. Three writes could not be confirmed. Symphonia will reconcile them before offering a retry.

Status shall never rely only on color. Keyboard navigation, visible focus, semantic headings, accessible tables/lists, and screen-reader announcements for material state changes are required.

## 10. Failure and recovery semantics

| Failure | Required behavior | User recovery |
|---|---|---|
| Source changes before acceptance | Mark plan stale; issue no writes | Recalculate and review a new revision |
| Connection expires before execution | Pause without losing progress | Reauthorize, then resume |
| Target capability changes | Stop before incompatible writes; record evidence | Re-plan or choose another target |
| Target creation response is unknown | Search/reconcile using stored intent and marker; do not blindly create again | Wait for reconciliation or inspect candidates |
| Entry batch response is unknown | Reconcile target contents/checkpoint before retry | Resume only when safe |
| Rate limit | Enter `waiting_rate_limit` with next eligible time | Automatic bounded resume; cancellation remains available |
| Some items fail permanently | Finish as `partial` with per-item reasons | Create a new remediation plan for failed entries |
| Process or host restarts | Resume from durable checkpoint and lease rules | No manual action unless state becomes uncertain |
| User cancels | Stop scheduling further writes; preserve confirmed results | Review partial result; cancellation is not rollback |

## 11. Security and privacy

- Acceptance and execution require authorization for the source projection and target connection.
- UI, logs, events, and exports shall not expose access or refresh tokens.
- Stored target item identifiers and playlist contents are household data and follow the project retention policy.
- Audit records include actor, connection reference, source snapshot, plan digest, timestamps, and outcome, but not provider secrets.
- Provider text, artwork, and URLs are untrusted input and must be safely rendered.
- Any destructive future behavior such as replacement or clearing requires a separate threat review and explicit confirmation contract.

## 12. Observability and supportability

Each plan and operation has a non-secret correlation identifier. Structured events cover plan creation, classification totals, acceptance, dispatch, target reconciliation, batch checkpoints, waits, retries, cancellation, and terminal result.

Metrics may include duration, plan size, classification counts, confirmation latency, retry counts, rate-limit waits, and terminal states. Labels shall not contain playlist names, track titles, user tokens, or unbounded provider identifiers.

A redacted diagnostic export shall contain the plan version and digest, adapter versions, capability snapshot, state history, checkpoints, and categorized failures.

## 13. Rollout, migration, and compatibility

The capability remains unavailable until its dependencies are ready for implementation and the blocking product policies are decided. Initial rollout shall use synthetic provider adapters, then provider sandboxes or tightly controlled accounts before general availability.

Persisted plans and operations require explicit schema versions. Migrations shall preserve accepted digests and audit history or fail safely before execution. An in-flight operation may resume only when the new version proves checkpoint compatibility.

## 14. Numeric test budget

Minimum planned automated tests: **94**.

| Area | Minimum |
|---|---:|
| Plan calculation, ordering, duplicates, and classifications | 24 |
| State transitions, digest validation, idempotency, and reconciliation | 22 |
| Provider capability and write adapter contracts | 18 |
| UI states and accessibility | 12 |
| Integration, restart, migration, security, and redaction | 18 |

Required fault injection includes timeouts before and after provider acceptance, duplicate delivery, process death at every write checkpoint, expired authorization, rate limits, capability drift, and ambiguous reconciliation.

## 15. Documentation impact

Implementation shall update:

- user guidance for planning, review, execution, cancellation, and partial results;
- provider support tables with read/write and visibility capabilities;
- administrator guidance for credentials, storage, and diagnostics;
- privacy and retention documentation;
- the SDD catalog and traceability evidence.

## 16. Acceptance criteria

1. A user can select an imported playlist and authorized target connection.
2. Planning performs no target mutation.
3. Every source occurrence appears exactly once in the immutable plan, preserving order and duplicates.
4. The UI discloses every ambiguous, unmatched, unavailable, invalid, unsupported, and deliberately omitted occurrence.
5. Acceptance binds to a specific plan digest, source projection version, capabilities snapshot, and target intent.
6. A stale or modified plan cannot execute.
7. Execution survives restart without duplicating the target playlist or confirmed entries.
8. Unknown provider outcomes trigger reconciliation before retry.
9. Cancellation stops future work and accurately reports already confirmed writes.
10. Partial success has per-item explanations and a safe remediation path.
11. Logs and diagnostics contain no provider secrets.
12. The numeric test budget and required fault-injection scenarios pass.

## 17. Requirement traceability

| Requirement | Design location | Planned verification |
|---|---|---|
| `SYM-PL-001`–`SYM-PL-009` | Sections 5-11 | Planning, classification, acceptance, execution, collision, and recovery suites |
| `SYM-PROD-002`, `SYM-PROD-004`–`SYM-PROD-006` | Sections 6, 10, and 13 | Disclosure, attribution, state, error, and history tests |
| `SYM-PROV-010`, `SYM-PROV-019` | Sections 7-9 and 11 | Capability and reconciliation adapter contract suites |
| `SYM-ARCH-009`–`SYM-ARCH-010` | Sections 7 and 11 | Operation-aware retry and partial-result tests |
| `SYM-JOB-003`–`SYM-JOB-005` | Sections 7 and 11 | Checkpoint, restart, cancellation, and unknown-outcome tests |
| `SYM-TEST-004`, `SYM-TEST-006` | Section 15 | Required fault and playlist-edge-case release gates |

## 18. Sequence sketch

```text
User -> App: choose source and target
App -> Import store: capture stable source projection
App -> Identity service: resolve each occurrence
App -> Provider adapter: read capabilities and target availability
App -> Plan store: persist immutable revision + digest
App -> User: show dry run and blockers
User -> App: accept exact digest
App -> Job store: enqueue durable copy operation
Worker -> Provider adapter: create/reconcile target
Worker -> Provider adapter: add/reconcile ordered batches
Worker -> Job store: checkpoint every confirmed result
App -> User: show terminal and per-item outcomes
```

## 19. Definition of done

- Blocking decisions are resolved and recorded in ADRs or the relevant horizontal specifications.
- Dependencies are at least `Ready for implementation`.
- Threat model and provider write contract reviews are complete.
- Tests meet the numeric budget and fault-injection requirements.
- Documentation and catalog evidence are current.
- Product owner explicitly approves implementation and later release.

## 20. References

- [SDD standard](README.md)
- [SDD catalog](CATALOG.md)
- [Recording identity resolution SDD](recording-identity-resolution.md)
- [Durable operations and recovery SDD](durable-operations-and-recovery.md)
