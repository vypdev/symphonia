# System architecture

**Status:** Home Assistant-first deployment accepted; logical boundaries proposed; technology stack open
**Last reviewed:** 2026-09-20

## Architectural drivers

The architecture is derived from these needs:

- long-running, self-hosted operation on modest hardware;
- a primary Supervisor-managed Home Assistant App experience similar to `vypdev/homeassistant-gateway`;
- a management UI that follows current Home Assistant component, theme, responsive, and interaction patterns without depending on private frontend internals;
- a core that can run and be tested without Home Assistant;
- provider-independent domain and replaceable adapters;
- durable imports and provider writes that survive restarts;
- explicit uncertainty, partial success, rate limiting, and user action;
- secure storage and rotation of OAuth credentials;
- provider-contract tests without real accounts;
- a future native Home Assistant surface without duplicating domain policy; and
- simple backup, restore, upgrade, and diagnostics.

These drivers do not yet justify a programming language, web framework, frontend framework, or database product. The observable UI direction and compatibility-layer boundary are accepted separately in [ADR 0004](../decisions/0004-home-assistant-native-ui.md); that decision does not select a framework.

## Context and trust boundaries

```text
                         provider OAuth/API boundaries
                    ┌───────────┬────────────┬─────────┐
                    │ Spotify   │ YouTube    │ future  │
                    └─────▲─────┴─────▲──────┴────▲────┘
                          │ adapters   │           │
┌─────────────────────────┴───────────┴───────────┴──────────────┐
│ Symphonia service                                              │
│  web UI/API → application use cases → domain                   │
│                    │                 ↑                          │
│                    ├→ durable jobs → provider ports             │
│                    └→ repositories / secret store ports         │
└──────────▲───────────────────┬─────────────────────────────────┘
           │                   │
   HA Ingress / optional       └→ persistent data and backups
   companion integration
           │
┌──────────┴──────────┐
│ Home Assistant      │
│ Supervisor + Core   │
└─────────────────────┘
```

Provider APIs, the browser, Home Assistant/Supervisor, persistent storage, and future external API clients are separate trust boundaries. Network proximity is not authentication.

## Dependency rule

Dependencies point inward:

```text
presentation ──→ application ──→ domain
infrastructure ────────────────→ ports defined inward
composition ──→ concrete implementations
```

- **Domain** owns recording identity, playlist semantics, capabilities, plans, policies, and operation states. It imports no provider SDK, Home Assistant package, web framework, database driver, filesystem/config reader, or job framework.
- **Application** orchestrates use cases through ports and owns transaction/idempotency boundaries. It depends on domain types, not concrete adapters.
- **Infrastructure** implements provider, persistence, secret, clock, queue, and Home Assistant ports.
- **Presentation** maps Ingress/HTTP/UI requests and responses. It does not decide match, authorization, retry, or conflict policy.
- **Composition** selects the deployment profile and wires concrete implementations. It is the only layer that knows the full runtime graph.

This follows the useful boundary pattern in `homeassistant-gateway` without carrying that project's language, frameworks, or non-music policies into Symphonia automatically.

## Logical components

| Component | Responsibility | Explicit exclusions |
| --- | --- | --- |
| Web UI | Home Assistant-native-adjacent shell and component compatibility layer; connection setup, library/playlist views, resolution queue, copy preview, history, diagnostics | Provider tokens, matching policy, direct provider calls, private HA frontend modules |
| HTTP/API presentation | Authenticated input/output mapping, validation shape, request correlation | Domain decisions and raw exception exposure |
| Application use cases | Connect/disconnect, import, resolve, plan copy, execute copy, inspect operations | Provider-specific response types |
| Domain | Provider-independent entities, invariants, capability requirements, matching/copy/sync policy | IO and scheduling |
| Provider adapter host | OAuth/token refresh, pagination, normalized reads/writes/search, error translation | Cross-provider orchestration |
| Resolution engine | Candidate generation/evaluation and evidence production | Unversioned opaque decisions |
| Durable job runner | Leasing, scheduling, checkpoints, retry timing, cancellation | Business-policy invention |
| Persistence adapters | Transactions, migrations, retention, backup-safe storage | Provider API behavior |
| Secret store adapter | Encrypt/decrypt credential material and rotate key references | Returning plaintext to UI/logs |
| Observability | Structured logs, metrics, health/readiness, sanitized diagnostics | Provider payload dumping |
| Home Assistant adapter | Ingress identity and future native integration contract | Owning music domain rules |

## Presentation and Home Assistant-native UI boundary

The cross-cutting UI contract lives in the [Home Assistant-native UI specification](../product/home-assistant-ui-specification.md), is accepted by [ADR 0004](../decisions/0004-home-assistant-native-ui.md), and is made implementation-driving by the [UI foundation SDD](../../specs/home-assistant-native-ui.md).

```text
public HA/App context ─→ validated context adapter ─→ semantic UI tokens
browser/standalone fallback ────────────────────────┘
                                                    ↓
feature view model ─→ feature composition ─→ presentation-only components
       ↑                    │                       │
application API/use case ───┘                       └→ catalog/reference tests
```

Text equivalent: a validated adapter maps only supported Home Assistant App context, with deterministic browser/standalone fallbacks, into semantic tokens. Feature views combine application-owned view models with a presentation-only component package; catalog, accessibility, responsive, Ingress, and visual-reference tests verify the result.

The compatibility package owns tokens, component geometry, accessibility interaction, and layout helpers. It may depend on the selected frontend framework and presentation assets, but it must not import API clients, application/domain models, provider adapters, Home Assistant private modules, or parent-page DOM/storage. Feature views own orchestration and route state but consume component families through one public package boundary rather than styling parallel one-off controls.

Official Home Assistant documentation, design-portal examples, and current source are the primary evolving reference. Pinned `homeassistant-gateway` sources and screenshots are implementation evidence only. Any direct reuse of a Home Assistant component requires a documented public/versioned contract, supported-version matrix, fallback, and rollback path; superficial runtime availability in the parent frame is not a contract.

Theme, locale, direction, timezone, safe-area, and base-path facts are untrusted until the context adapter validates their supported message/origin/schema. They affect presentation and formatting only; they never grant authorization or change domain/application policy. Standalone composition supplies the same semantic inputs from its own authenticated profile and must preserve the same feature states and actions.

## Deployment model

### Primary: Home Assistant App

This is an accepted product/deployment decision, recorded in [ADR 0003](../decisions/0003-home-assistant-app-primary.md).

- Symphonia is packaged as a Supervisor-managed Home Assistant App (the current name for an add-on).
- The App starts as an `application`, stores durable state under `/data`, exposes its UI through Ingress, and participates in Supervisor backup/update lifecycle.
- Ingress is the administrative UI authentication boundary. The server MUST honor the Ingress base path and MUST NOT assume it is hosted at `/`.
- App permissions, mapped folders, network exposure, and Supervisor/Core API access MUST be least-privilege. Music-provider access alone does not justify Home Assistant API or host filesystem access.
- A published image MUST support the explicitly documented Home Assistant architectures; the initial architecture set is open.
- Provider secrets MUST NOT be placed in App options, image layers, logs, diagnostics, or ordinary backups in plaintext.

Home Assistant's current App documentation confirms that `/data` is persistent, Ingress can authenticate the UI, and App backup behavior is configurable. These platform facts are linked in [provider/platform research](../providers/provider-research.md#home-assistant-platform).

### Secondary: standalone service

To preserve the original “usable without Home Assistant” principle and test the core honestly, the same application core SHOULD have a standalone container/service composition profile.

The standalone profile has no Ingress. It therefore requires an explicit authentication and network-exposure policy, persistent volume mapping, health endpoints, backup procedure, and OAuth callback configuration. Standalone must not become a second product: domain behavior, migrations, provider adapters, and operation history remain shared.

Whether standalone packaging ships in the first public release or immediately afterward is open.

### Optional companion Home Assistant integration

A companion custom integration MAY later expose native entities, actions, events, and configuration discovery. It must call a stable, authenticated Symphonia API and MUST NOT duplicate matching, sync, credential, or retry logic.

The integration MAY also be evaluated as a narrow provider-authorization broker so Symphonia can reuse Home Assistant's Application Credentials/config-flow callback machinery. If selected, it must exchange an opaque, one-use connection grant over the authenticated local API; provider operation logic remains in the App. Token ownership, refresh, revocation, backup, failure recovery, and integration/App version skew must be specified before this is accepted.

Candidate native surface (illustrative, not accepted):

- sensors for connection health, unmatched count, running operations, and last successful sync;
- actions such as `symphonia.copy_playlist` and future `symphonia.sync`;
- events for operation completed, partial, failed, or user action required.

Three approaches require an RFC:

| Approach | Benefits | Costs |
| --- | --- | --- |
| Companion custom integration over local HTTP/WebSocket | Native actions/entities and clean separation; mirrors the gateway pattern | Another artifact and compatibility matrix |
| MQTT discovery/events | Mature decoupling and push model | Adds an MQTT dependency and weakens direct operation correlation |
| App calls Home Assistant APIs directly | Fewer artifacts for events/actions initiated by the App | Couples the service to Home Assistant and does not cleanly provide a native integration surface |

The companion-integration approach is the current leading direction, not yet an accepted implementation decision.

## Service/API shape

The backend needs an authenticated HTTP API for its own web UI and future integration adapter. The API SHOULD be resource/use-case oriented rather than a transparent provider proxy. It must never accept arbitrary provider URLs or expose raw upstream payloads by default.

Required conceptual endpoints/use cases include:

- connection list, capability probe, authorization start/callback, refresh, and disconnect;
- import start/status and collection reads;
- unresolved queue, candidate evidence, accept/reject/defer/revoke;
- copy plan, plan read, accept/execute, run status, reconcile/cancel where safe;
- operation history and issue resolution; and
- health, readiness, version, migration state, and sanitized diagnostics.

Public API versioning, pagination, error envelopes, and event streaming require an API RFC before implementation.

## Persistence requirements

- **SYM-ARCH-001:** Durable domain data, accepted plans, manual decisions, job checkpoints, and operation summaries MUST survive process and App restarts.
- **SYM-ARCH-002:** Persistence MUST support atomic state transitions between a job checkpoint and its audit outcome where they share a store.
- **SYM-ARCH-003:** Schema changes MUST use forward migrations, have backup/restore guidance, and be tested from every supported released version.
- **SYM-ARCH-004:** Imported provider payloads MUST carry freshness/retention metadata and be deletable independently from locally owned decisions.
- **SYM-ARCH-005:** Referential design MUST preserve historical operation meaning when a connection or provider item is removed.
- **SYM-ARCH-006:** Backup MUST either quiesce writes or use a transactionally consistent online method.
- **SYM-ARCH-007:** Restore MUST detect incompatible or partial data before starting background writes.

Conceptual stores:

- provider connections and credential references;
- recording/provider representation graph and resolution evidence;
- current imported projections plus immutable snapshots needed by active/history policy;
- copy plans and future sync relationships;
- durable job state, checkpoints, leases, and retry schedule;
- operation/audit records and issues; and
- application schema/version/configuration.

### Database alternatives

| Option | Fit | Trade-offs |
| --- | --- | --- |
| SQLite under `/data` | Excellent single-user/App simplicity, transactional, easy backup when handled correctly | One-writer behavior and queue/lease design need care; multi-replica is inappropriate |
| PostgreSQL | Strong concurrency and operational tooling | Separate service/configuration is burdensome for a small Home Assistant install |
| Embedded key-value/document store | Simple packaging for some access patterns | Relational identity/history queries and migrations become harder |

SQLite is the leading MVP candidate because the expected deployment is a single App instance, but it is **not accepted** until concurrency, backup, retention, and migration spikes are complete.

## Background job and synchronization execution

Imports and provider writes are asynchronous operations backed by durable state, not process-local tasks.

- **SYM-JOB-001:** Job states MUST include at least `queued`, `running`, `waiting_rate_limit`, `waiting_user`, `retry_scheduled`, `succeeded`, `partial`, `failed`, and `cancelled`.
- **SYM-JOB-002:** A worker MUST acquire a time-bounded lease; abandoned running work becomes eligible for recovery after lease expiry.
- **SYM-JOB-003:** Every write step MUST have a stable idempotency/reconciliation key and a persisted before/after checkpoint.
- **SYM-JOB-004:** Retry schedules MUST survive restart and MUST respect provider retry hints and a configured attempt/time budget.
- **SYM-JOB-005:** Cancellation MUST be cooperative. Completed provider writes remain recorded and are not described as rolled back unless compensating writes actually succeeded.
- **SYM-JOB-006:** Scheduling MUST be fair across connections and MUST honor provider-, account-, and operation-specific concurrency limits.
- **SYM-JOB-007:** The UI MUST receive progress from persisted operation state; live in-memory events may accelerate display but are not authoritative.
- **SYM-JOB-008:** Scheduler time MUST use UTC instants; user-facing schedules and timestamps use the configured Home Assistant or standalone timezone explicitly.

Initial process topology alternatives:

1. **One modular process with API, scheduler, and bounded worker pool.** Simplest App lifecycle; requires careful shutdown and resource isolation.
2. **One image supervising separate API and worker processes.** Better isolation; more complex coordination and health semantics inside an App.
3. **External workflow/queue service.** Powerful but disproportionate for the single-node MVP.

Option 1 is the proposed starting point. Durable database state—not the process—is the queue authority, so a later split does not change domain semantics.

## Error model and retries

Adapters normalize provider failures into stable categories while retaining sanitized provider codes:

| Category | Default behavior |
| --- | --- |
| `authentication_required` / `authorization_revoked` | No blind retry; mark connection action-required |
| `permission_denied` / `capability_unavailable` | Permanent for the plan; return to planning/user |
| `not_found` / `item_unavailable` | Re-import/reconcile once if staleness is plausible; otherwise item issue |
| `invalid_request` | Permanent implementation/plan failure; no retry storm |
| `rate_limited` | Schedule from `Retry-After`/reset signal or conservative adapter policy |
| `provider_unavailable` / timeout / network | Exponential backoff with jitter and finite budget |
| `conflict` / version changed | Re-import and re-plan or surface conflict; never overwrite silently |
| `unknown_write_outcome` | Reconcile target state before any retry |
| `provider_contract_changed` | Stop affected capability, flag adapter health, require code/evidence update |

- **SYM-ARCH-008:** Error messages crossing a boundary MUST be sanitized and correlated; tokens, authorization codes, raw headers, and unrestricted payloads MUST be absent.
- **SYM-ARCH-009:** Retry policy MUST be operation-aware. A retryable HTTP status does not by itself make a non-idempotent write safe.
- **SYM-ARCH-010:** Partial success MUST be a first-class terminal or waiting state with item-level facts.

## Rate-limit model

- **SYM-ARCH-011:** Each adapter MUST expose known quota dimensions, observed remaining/reset hints, and conservative defaults when limits are undocumented.
- **SYM-ARCH-012:** Rate limiting MUST occur before requests using per-provider/per-connection budgets and after responses using provider hints.
- **SYM-ARCH-013:** Interactive reads MAY receive higher scheduling priority than background refresh, but MUST NOT bypass hard limits.
- **SYM-ARCH-014:** Search-heavy matching MUST use caches and bounded candidate queries consistent with provider retention rules.
- **SYM-ARCH-015:** An operation plan SHOULD estimate known request/quota cost and warn when completion is unlikely within the current budget.

## Authentication and credentials

There are three distinct concerns:

1. **Administrative access to Symphonia.** In Home Assistant mode this is primarily Ingress identity. Standalone authentication is open and MUST NOT default to unauthenticated non-loopback exposure.
2. **Provider OAuth client credentials.** Self-hosters may need to register their own applications. Client secrets and registration configuration are different from user grants.
3. **Provider user grants.** Access/refresh tokens authorize external music operations and need revocation, expiry, and minimum-scope handling.

- **SYM-SEC-001:** Provider authorization MUST use the currently recommended authorization-code flow for the deployment/client type, CSRF `state`, exact redirect validation, and PKCE where applicable.
- **SYM-SEC-002:** Symphonia MUST request the minimum scopes needed for enabled capabilities and show them before consent.
- **SYM-SEC-003:** Tokens and client secrets MUST be encrypted at rest with key material kept outside the data database/ordinary export. If a platform cannot provide a separate secret, setup MUST make the trade-off explicit.
- **SYM-SEC-004:** Plaintext secrets MUST exist only for the shortest practical call boundary and MUST be redacted from logs, exceptions, metrics, traces, UI state, fixtures, and support bundles.
- **SYM-SEC-005:** Disconnect MUST revoke grants when supported, erase local credential material, disable jobs, and start provider-data cleanup.
- **SYM-SEC-006:** Authorization callbacks MUST bind provider, connection attempt, initiating user/session, state, redirect target, and an expiry; callbacks are single-use.
- **SYM-SEC-007:** Credential refresh MUST use a single-flight lock per connection to avoid destructive refresh-token races.
- **SYM-SEC-008:** Ingress identity headers MUST only be trusted on the verified Ingress listener/path; direct listeners MUST use their own authentication.
- **SYM-SEC-009:** A directly exposed OAuth callback listener MUST expose only the minimum callback surface or independently authenticate every other route. Opening a callback port MUST NOT make the management UI/API anonymously reachable.
- **SYM-SEC-010:** Provider-controlled IDs, names, URIs, metadata, callback parameters, and adapter mappings MUST NOT become local filesystem paths, module/import names, executable URI schemes, arbitrary redirect targets, or unrestricted outbound destinations.
- **SYM-SEC-011:** The App MUST run without root privileges where the platform permits and MUST NOT request host/config/media mounts or broad network privileges without a documented requirement and threat review.

### OAuth callback risk in Home Assistant mode

Provider redirect URIs must be exact and externally reachable under provider rules, while Home Assistant Ingress uses a proxied base path and session. The official Home Assistant Spotify integration demonstrates `https://my.home-assistant.io/redirect/oauth` and `<HOME_ASSISTANT_URL>/auth/external/callback` through Home Assistant's Application Credentials/config-flow machinery. A Supervisor App does not automatically inherit that machinery; using it would require a companion integration or another explicitly designed broker.

The project MUST complete an OAuth callback spike for local-only and externally reachable Home Assistant deployments before provider authentication architecture is accepted. It must compare a direct App flow with a minimal companion-integration authorization broker and cover HTTPS, redirect registration, Ingress session continuity, remote access, dynamic paths, user-provided OAuth clients, state/PKCE/single use, denial/error flows, token ownership, integration/App version skew, backup/restore, and reauthorization. Any direct callback port must satisfy `SYM-SEC-009`. Tokens MUST NOT be pasted into App options or browser-export files as a normal workaround.

See the dated [Home Assistant music ecosystem review](../providers/home-assistant-ecosystem-review.md) for the implementation evidence and security cautions behind these alternatives.

## Observability

- **SYM-OBS-001:** Every operation and provider request attempt MUST carry correlation identifiers for operation, run, step, connection, and adapter; provider object IDs are logged only under a documented privacy policy.
- **SYM-OBS-002:** Structured logs MUST record category, sanitized provider code, attempt, duration, and outcome without request/response bodies by default.
- **SYM-OBS-003:** Health means the process is alive; readiness additionally covers migrations, writable persistence, scheduler state, and ability to serve without claiming every provider is online.
- **SYM-OBS-004:** Metrics MUST cover queue depth/age, operation outcomes/duration, provider requests/latency/errors/throttles, resolution states, import freshness, and worker lease recovery.
- **SYM-OBS-005:** Diagnostics MUST be bounded, user-previewable, and safe to share. Secret-redaction tests are release gates.
- **SYM-OBS-006:** Audit history MUST say what Symphonia intended, attempted, observed, and could not determine.

The MVP may render metrics in its UI and logs; choosing Prometheus/OpenTelemetry or another export is a later implementation decision.

## Home Assistant contract

- **SYM-HA-001:** The primary release artifact MUST be installable as a Supervisor-managed Home Assistant App from a documented repository.
- **SYM-HA-002:** The App MUST expose its management UI through Ingress and support Ingress-relative routing.
- **SYM-HA-003:** App restart, Supervisor backup/restore, and upgrade MUST preserve durable state and safely recover jobs.
- **SYM-HA-004:** Domain and application modules MUST NOT import Home Assistant or Supervisor libraries.
- **SYM-HA-005:** Home Assistant unavailability MUST NOT corrupt provider operations; future native surfaces report unavailable and recover.
- **SYM-HA-006:** A companion integration, if built, MUST consume a versioned local Symphonia contract and MUST NOT access the database or token store directly.
- **SYM-HA-007:** Native entities/actions/events MUST expose bounded summaries or identifiers, not playlist contents, tokens, or raw provider errors in state attributes.
- **SYM-HA-008:** Home Assistant automations that trigger mutations MUST create ordinary audited Symphonia operations subject to the same validation, idempotency, and policy as UI requests.
- **SYM-HA-009:** The MVP App panel MUST be admin-only; a future multi-user model MUST define which Home Assistant identity owns provider connections and may approve writes.

## Technology decisions still open

| Concern | Reason not yet chosen | Evidence needed |
| --- | --- | --- |
| Backend language/framework | Provider SDK maturity, job ergonomics, footprint, HA App maintainability | Thin vertical spike and maintainer preference |
| UI framework/build tooling | The Home Assistant-native component, accessibility, catalog, Ingress, and standalone contracts are accepted, but the implementation technology remains reversible | `RG-006` prototype proving public context, package boundaries, bundle/compatibility cost, catalog and browser evidence |
| SQLite versus PostgreSQL | Concurrency, backup, migration, and library scale unmeasured | Storage/job lease spike and target sizes |
| Job library versus internal durable runner | Retry/idempotency needs are specific; external brokers add operations | Failure/restart spike |
| Secret encryption/key source | HA App secret facilities and portable standalone behavior differ | Threat model and backup/restore test |
| Companion integration transport | Need push, authentication, discovery, and version compatibility | Home Assistant integration RFC |
| Public API/event protocol | Only internal UI needs are currently concrete | UI and companion-integration contract design |

No implementation agent should infer these technology choices from examples in `homeassistant-gateway`. The Gateway informs the accepted presentation boundary and verification approach, not an automatic dependency or stack selection.
