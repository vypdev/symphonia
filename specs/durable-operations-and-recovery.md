# Durable operations and recovery

- Status: Draft
- Date: 2026-09-20
- Catalog capability ID: `durable-operations-and-recovery`
- Owners: Symphonia maintainers
- Scope: execute imports and provider writes through durable, observable operations that recover safely across restarts, rate limits, uncertain writes, and upgrades.
- Related requirements: `SYM-PROD-004`–`SYM-PROD-006`, `SYM-ARCH-001`–`SYM-ARCH-002`, `SYM-ARCH-005`, `SYM-ARCH-008`–`SYM-ARCH-010`, `SYM-JOB-001`–`SYM-JOB-008`, `SYM-OBS-001`–`SYM-OBS-006`, `SYM-TEST-004`, `SYM-TEST-013`, `SYM-DEP-002`, `SYM-DEP-008`
- Related decisions/research: [system architecture](../docs/architecture/system-architecture.md), [development specification](../docs/development/development-specification.md), [ADR 0004](../docs/decisions/0004-home-assistant-native-ui.md), [UI foundation](home-assistant-native-ui.md), `RG-004`
- Required review gates: architecture, persistence/recovery, provider contracts, testing, documentation, security/operations
- Open decisions blocking readiness: persistent store; worker/process topology; lease and retention parameters; supported migration strategy; representative operation sizes and timing targets

## 1. Executive summary

Symphonia shall execute imports, provider reads, identity work, and playlist writes as durable operations whose authoritative state survives process restarts, Home Assistant App upgrades, temporary provider failures, and rate limits.

The operation engine shall use explicit state transitions, bounded leases, idempotency keys, checkpoints, and reconciliation. It shall never equate an in-memory task with durable progress or blindly retry a provider mutation whose outcome is unknown.

## 2. Problem statement and evidence

Provider work crosses unreliable networks and may take longer than an HTTP request or Home Assistant lifecycle event. A process may stop after a provider accepted a write but before Symphonia recorded the response. Without a durable contract, retrying can duplicate playlists or entries, while abandoning work can leave invisible partial results.

The product, architecture, and provider specifications require resumability, rate-limit awareness, explicit partial outcomes, auditable state, and safe operation in the Home Assistant App lifecycle.

An owner-approved foundation slice now proves a dependency-free SQLite operation repository, leases, checkpoints, retries, cancellation, recovery events, bounded diagnostics with capped key lists, provider-independent handlers, shared SQLite connection policy with foreign-key enforcement and bounded lock waits, JSON-object/string-key payload validation, and deterministic worker tests. The capability SDD remains `Draft`: persistent-store and worker-topology decisions, retention, migration strategy, representative sizing, and the complete provider/UI vertical slice are still open. This evidence does not authorize production operation policy or claim that the full capability is implemented.

Evidence sources:

- [Product specification](../docs/product/product-specification.md)
- [System architecture](../docs/architecture/system-architecture.md)
- [Provider specification](../docs/providers/provider-specification.md)
- [Development specification](../docs/development/development-specification.md)

## 3. Actors and authorization

- Application services create operations on behalf of an authenticated, authorized actor or a future explicitly approved scheduler.
- Workers claim and advance operations.
- Provider adapters report safe-retry, wait, permanent-failure, and unknown-outcome information.
- Administrators inspect, cancel, resume, or export diagnostics through authorized interfaces.

Workers do not gain broader provider or household access merely by reading a queued operation. The stored operation references a scoped connection and authorization context.

## 4. Goals, non-goals, and invariants

### Goals

- Persist operation intent before side effects begin.
- Recover automatically from expected restarts and transient failures.
- Prevent concurrent workers from advancing the same step unsafely.
- Make retry timing, progress, partial results, and required user action visible.
- Reconcile unknown provider outcomes before any repeated mutation.
- Support versioned schema and application upgrades.

### Non-goals

- A general-purpose distributed workflow platform.
- Exactly-once delivery claims across third-party providers.
- Infinite automatic retry.
- Hiding permanent or ambiguous failures behind a success state.
- Automatic rollback of irreversible provider mutations.

### Invariants

- The persistent store, not worker memory, is authoritative.
- Intent and an idempotency key are persisted before an external side effect.
- Only the current lease holder may checkpoint a running step.
- Leases expire and are recoverable; they are never permanent locks.
- A step with unknown external outcome enters reconciliation before retry.
- State transitions are validated, atomic, and auditable.
- Terminal results are immutable except for separately recorded reconciliation or remediation operations.
- Cancellation prevents future work but does not rewrite confirmed history.

## 5. User journey and operational flow

1. An application service validates a requested action and stores its immutable intent, actor context, and idempotency key.
2. The same transaction or a recoverable dispatch mechanism makes the operation eligible for work.
3. A worker atomically claims a time-bounded lease.
4. The worker loads the last durable checkpoint and validates operation/schema compatibility.
5. Before each provider side effect, the worker records the intended step and reconciliation data.
6. The worker performs the call, categorizes the result, and atomically checkpoints confirmed progress.
7. It renews the lease only while healthy, releases it when waiting, or records a terminal result.
8. The UI reads persisted state and events rather than subscribing only to a worker process.

After a crash, another worker waits for lease expiry, claims the operation, and resumes from the last confirmed checkpoint. If a call may have succeeded externally, it reconciles that step first.

## 6. Functional contract and state model

### Operation states

- `queued`: eligible for a worker.
- `running`: actively owned by a valid lease.
- `waiting_rate_limit`: paused until a recorded provider-safe time.
- `waiting_user`: requires an explicit user decision or renewed authorization.
- `retry_scheduled`: transient failure with a bounded next attempt time.
- `succeeded`: all required outcomes confirmed.
- `partial`: work ended with a mix of confirmed success and disclosed permanent failure or exclusion.
- `failed`: the operation cannot safely achieve its required outcome.
- `cancelled`: cancellation was accepted and no more work will be scheduled.

### Step outcome categories

- `confirmed_success`
- `safe_retry`
- `rate_limited`
- `authorization_required`
- `permanent_failure`
- `unknown_outcome`
- `cancelled_before_start`

`unknown_outcome` is not a retry category. It creates a reconciliation step whose result may be confirmed success, confirmed absence followed by safe retry, or `waiting_user`/`failed` if it cannot be determined safely.

### Transition rules

- Terminal states cannot transition back to `running`.
- Remediation of a terminal operation creates a linked new operation.
- `running` requires an unexpired lease token and owner.
- `waiting_rate_limit` and `retry_scheduled` store an absolute next-eligible time plus the source of that timing.
- `waiting_user` stores a redacted reason and a bounded set of permitted actions.
- Cancellation is checked before claim, before every side effect, and between provider batches.

### Idempotency

The operation request key deduplicates logically identical submissions within a defined scope. Each external mutation step has a stable key or reconciliation fingerprint derived from immutable intent—not from an attempt count. Where a provider lacks idempotency support, the adapter shall supply a deterministic reconciliation strategy or declare the write unsupported.

## 7. Configuration contract

| Setting | Scope | Default | Validation and notes |
|---|---|---|---|
| Global worker concurrency | App | Conservative | Bounded by CPU/memory and provider fairness. |
| Per-provider concurrency | Adapter | Provider-specific | Must respect documented and observed limits. |
| Lease duration | Runtime | To be determined by spike | Must exceed normal checkpoint interval and remain recoverable. |
| Lease renewal interval | Runtime | Fraction of lease duration | Renewal failure stops new side effects. |
| Maximum attempts | Operation class | Bounded | Permanent and unknown outcomes bypass blind retry. |
| Backoff policy | Adapter | Exponential with jitter, capped | Honors provider retry hints when safe. |
| Event retention | App | Pending privacy/storage decision | Terminal summary and audit requirements may outlive verbose events. |
| Diagnostic retention | App | Pending policy | Redacted and bounded. |

Users may cancel operations, but they shall not be offered arbitrary knobs that weaken lease safety, idempotency, retention obligations, or provider rate-limit compliance.

## 8. Architecture and boundaries

### Domain layer

Defines operation intent, states, steps, attempts, outcome categories, cancellation, and transition invariants without depending on a queue library, database driver, Home Assistant, or provider SDK.

### Application layer

Creates operations, schedules eligibility, claims leases, dispatches handlers, checkpoints progress, performs reconciliation, and publishes redacted progress views.

### Ports

- Transactional operation repository.
- Clock and unique identifier source.
- Eligibility notification/wakeup mechanism.
- Operation handler registry.
- Provider reconciliation and rate-limit advice.
- Audit event sink and redacted diagnostic exporter.

### Adapters

- A selected persistent store implements atomic transitions and leases.
- The runtime may use an in-process worker initially, but correctness cannot depend on it staying alive.
- Provider adapters translate API responses into the shared outcome categories.
- Home Assistant App lifecycle hooks request graceful shutdown and expose health; they do not own job truth.

The persistent store and wakeup mechanism may be one technology or separate ones. The design shall not require an external broker unless evidence justifies that operational cost.

## 9. UI, UX, and accessibility

Operation list/detail, progress, wait, recovery, cancellation, reconciliation, and terminal-result surfaces conform to the [Home Assistant-native UI foundation](home-assistant-native-ui.md). They use shared statuses, alerts, progress/loading, cards/sections, responsive result rows/tables, buttons, and adaptive dialogs. Visual updates are projections of persisted operation state; component animation or in-memory events can improve immediacy but never invent progress or success.

The operations view shall show action type, actor-safe label, creation time, current state, progress numerator/denominator when meaningful, next retry time, and available actions.

Example running state:

> Copying playlist: 78 of 124 entries confirmed. You can leave this page; the operation will continue.

Example rate-limit state:

> The provider asked Symphonia to wait. The next attempt is scheduled for 14:32. No action is required.

Example user-action state:

> This connection needs authorization before the operation can continue. Reauthorize or cancel.

Example recovery state:

> Symphonia restarted while a provider request was in progress. It is checking the provider before continuing to avoid duplicate changes.

Progress shall not move backward without an explicit explanation. Status shall not rely only on color, and live updates shall use non-disruptive accessible announcements.

## 10. Failure and recovery semantics

| Failure | Required behavior | Recovery |
|---|---|---|
| Worker crashes before side effect | Lease expires; checkpoint remains authoritative | Another worker safely resumes |
| Worker crashes after external acceptance but before checkpoint | Step remains uncertain | Reconcile externally before deciding success or retry |
| Store unavailable | Stop new external side effects; do not rely on memory-only progress | Resume after durable store health returns |
| Lease renewal fails | Stop starting side effects and relinquish/expire ownership | Another claim after store recovery and lease expiry |
| Duplicate dispatch | Atomic claim permits one active lease | Extra dispatch becomes a no-op |
| Rate limit | Persist provider advice and release active execution | Become eligible at safe time |
| Authorization expires | Persist `waiting_user`; retain checkpoint | Resume after scoped reauthorization |
| Repeated transient failure | Apply bounded backoff and attempt ceiling | End `failed` with remediation guidance |
| Permanent item failures | Continue only when operation policy permits | End `partial` with per-item results |
| Incompatible application/schema upgrade | Do not claim or mutate externally | Run verified migration or require operator action |
| Cancellation races with a provider call | Reconcile the in-flight call; start no later steps | Report confirmed partial state accurately |

Graceful shutdown stops new claims, lets safe checkpoints finish within a bounded interval, and then releases or permits leases to expire. Correctness must also hold for abrupt termination.

## 11. Security and privacy

- Operation payloads store credential references, never raw tokens.
- Payloads, results, and diagnostics are classified and minimized; playlist contents and provider identifiers are household data.
- Every administrative action is authorized and audited.
- Handlers validate payload schema and version before use.
- Logs exclude secrets and avoid full provider response bodies by default.
- Retry and error messages displayed in the UI are redacted and safe for the current actor.
- Queue/store corruption, forged state transitions, and lease theft are included in the threat model.

## 12. Observability and supportability

Structured events include operation creation, eligibility, claim, renewal, checkpoint, wait, retry schedule, reconciliation, cancellation, and terminal transition. Each event includes operation ID, operation type, state, attempt count, adapter category, and bounded error code; it excludes credentials and unbounded content.

Metrics include queue depth, oldest eligible age, running leases, expired lease recoveries, state counts, execution latency, wait duration, attempt counts, unknown outcomes, reconciliation results, and terminal result ratios. Cardinality shall remain bounded.

Health distinguishes API availability, persistent-store readiness, worker liveness, claim progress, and migration state. A redacted export provides state history, version information, checkpoints, lease history, and categorized errors.

## 13. Rollout, migration, and compatibility

Before implementation readiness, a persistence spike shall prove atomic claim, lease expiry, transactional checkpointing, backup/restore behavior under `/data`, and migration safety in the chosen Home Assistant App runtime.

Operation records and payloads carry explicit schema and handler versions. Upgrade tests cover queued, running, waiting, partial-progress, cancelled, and terminal fixtures. A version that cannot safely resume an operation shall leave it untouched and expose an actionable incompatibility state rather than guessing.

Initial rollout uses one App instance and conservative concurrency. Multi-instance execution is out of scope unless a later deployment model requires it, but lease semantics shall not depend on process-local mutexes.

## 14. Numeric test budget

Minimum planned automated tests: **86**.

| Area | Minimum |
|---|---:|
| Domain states, transitions, cancellation, and invariants | 20 |
| Claims, leases, races, checkpoints, idempotency, and reconciliation | 24 |
| Persistence and provider outcome adapter contracts | 16 |
| UI states and accessibility | 8 |
| Integration, restart, migration, security, corruption, and redaction | 18 |

Required deterministic tests include duplicate dispatch, concurrent claim, lease expiry, clock boundaries, crash before/after every checkpoint, store outage, retry exhaustion, rate-limit timing, cancellation races, unknown outcomes, and compatible/incompatible upgrades.

The eight feature-specific UI cases supplement the UI-foundation budget and inherit its component-catalog, host-context, accessibility, responsive, theme/localization, hostile-content, and dated visual-reference gates.

## 15. Documentation impact

Implementation shall update:

- administrator guidance for storage, backup, restore, shutdown, and diagnostics;
- user guidance for progress, waits, cancellation, partial results, and recovery;
- architecture documentation with the selected store and worker topology;
- privacy/retention documentation;
- runbooks for stuck operations, migration failures, and provider reconciliation;
- the SDD catalog and traceability evidence.

## 16. Acceptance criteria

1. Operation intent and idempotency data are durable before any external side effect.
2. State transitions are atomic, validated, and auditable.
3. Only one valid lease holder can advance an operation step.
4. A restart at every defined checkpoint resumes without losing confirmed progress.
5. Unknown provider outcomes enter reconciliation and never blind retry.
6. Duplicate submissions and duplicate dispatches do not duplicate logical work.
7. Rate limits and transient failures produce bounded, visible waits.
8. Expired authorization produces `waiting_user` without discarding progress.
9. Cancellation starts no later work and accurately accounts for in-flight outcomes.
10. Store unavailability prevents new external side effects.
11. Supported upgrades preserve or safely refuse every persisted state fixture.
12. Logs, metrics, events, and diagnostics contain no credentials or prohibited content.
13. The numeric test budget and fault-injection suite pass.
14. Queued, running, rate-limited, retry-scheduled, waiting-user, recovering, reconciling, partial, failed, cancelled, and succeeded fixtures use shared Home Assistant-native components; updates preserve focus, never move progress backward without explanation, and remain truthful after disconnect/reload at narrow and wide widths.

## 17. Requirement traceability

| Requirement | Design location | Planned verification |
|---|---|---|
| `SYM-JOB-001`–`SYM-JOB-008` | Sections 6-11 | State, lease, checkpoint, retry, fairness, time, cancellation, and reconciliation suites |
| `SYM-PROD-004`–`SYM-PROD-006` | Sections 6, 10, and 13 | Attribution, persisted state, item-failure, and error tests |
| `SYM-ARCH-001`–`SYM-ARCH-002`, `SYM-ARCH-005`, `SYM-ARCH-008`–`SYM-ARCH-010` | Sections 5-14 | Durability, atomicity, history, sanitation, retry, and partial-result tests |
| `SYM-OBS-001`–`SYM-OBS-006` | Section 13 | Correlation, event, metric cardinality, health, diagnostic, and audit tests |
| `SYM-TEST-004`, `SYM-TEST-013` | Sections 14-15 | Provider-write fault and migration release gates |
| `SYM-DEP-002`, `SYM-DEP-008` | Sections 6, 11, and 14 | App restart and graceful/abrupt shutdown tests |

## 18. Sequence sketch

```text
Application service -> Operation store: persist intent + idempotency key
Application service -> Wakeup adapter: signal eligibility
Worker -> Operation store: atomically claim bounded lease
Worker -> Operation store: persist step intent + reconciliation fingerprint
Worker -> Provider adapter: perform external call
alt confirmed response
  Worker -> Operation store: checkpoint confirmed result
else unknown response
  Worker -> Operation store: persist reconciliation-required state
  Worker -> Provider adapter: inspect external state
  Worker -> Operation store: record reconciled result
end
Worker -> Operation store: wait, continue, or terminal transition
UI -> Operation store: read durable progress view
```

## 19. Definition of done

- Persistent store and worker topology decisions are recorded in ADRs.
- The persistence spike demonstrates required atomicity, restart, and migration behavior.
- Threat model and failure-mode review are complete.
- Operation handlers for the first vertical capability pass the shared contract suite.
- Tests meet the numeric budget and deterministic fault-injection requirements.
- Runbooks, user/admin documentation, and catalog evidence are current.
- Project owner explicitly approves implementation and later release.

## 20. References

- [SDD standard](README.md)
- [SDD catalog](CATALOG.md)
- [Home Assistant App runtime and Ingress SDD](home-assistant-app-runtime-and-ingress.md)
- [One-time playlist copy SDD](one-time-playlist-copy.md)
- [Home Assistant-native UI foundation SDD](home-assistant-native-ui.md)
- [ADR 0004](../docs/decisions/0004-home-assistant-native-ui.md)
