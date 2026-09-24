# Implementation baseline

**Status:** owner-approved foundation slice
**Last reviewed:** 2026-09-22

The first implementation increment is intentionally narrower than any provider or Home Assistant capability. It proves the provider-independent core and the durable-operation persistence contract without selecting an external web framework, provider SDK, OAuth strategy, or frontend stack.

## Current slice

- Python 3.11+ package under `src/symphonia`.
- Dependency-free domain values for ordered playlist snapshots, the six product entry classifications, copy policies, immutable copy plans, and acceptance digests.
- Dependency-free SQLite operation repository proving idempotent creation, time-bounded worker leases, checkpoint ownership, retry scheduling, and expired-lease recovery.
- Atomic scheduler-facing claim selection for queued, due-retry, and expired-lease operations.
- Append-only SQLite operation event history for auditable transitions with sanitized checkpoint summaries.
- Bounded redacted operation diagnostics for support and a future authenticated operations view, with hard item/event caps.
- Diagnostic payload/checkpoint key lists are capped at 100 entries and mark truncation.
- Diagnostic event queries fetch only the requested window plus one row to determine truncation.
- Bounded recent-operation diagnostics listing that exposes only redacted support views.
- Aggregate operation queue summaries expose state counts, eligible age, and expired leases without payload data.
- Explicit provider rate-limit waits with absolute retry times and durable eligibility.
- Bounded transient retry budgets for copy and import handlers with durable exhaustion outcomes.
- Lease-expiry recovery is audited distinctly from first claims, with prior worker identity retained only as metadata.
- Provider connection persistence with account uniqueness, opaque secret references, health states, and effective capability evidence.
- Application connection service for verified-account registration, capability probes, degraded health, and reauthorization-required classification.
- Pure capability-layer intersection and requirement checks for adapter/connection/object/health constraints.
- Durable operation runner that atomically claims eligible work and fails unwired operation types before side effects.
- The operation runner validates handler result type and operation identity before returning a claimed result.
- Cooperative single-process operation worker with interruptible polling and injected clock support.
- Copy executor can run as a claimed operation handler, preserving the same restart/checkpoint semantics under the runner.
- Playlist import executor persists intent before reads and reports succeeded, partial, waiting-user, retry, and rate-limit outcomes durably.
- Provider-neutral authorization attempts with hashed state, exact redirect binding, expiry, and single-use consumption.
- Direct-callback authorization can resolve a durable attempt by the returned state digest after restart without persisting raw state; ambiguous digests fail closed.
- Authorization consumption is covered across independent SQLite connections so callback replay races produce exactly one consumed attempt.
- Authorization state is bounded before hashing, required identifiers are validated before SQLite writes, and durable failure codes use a bounded safe alphabet.
- Application authorization boundary that generates one-use state without persisting the raw value.
- Authorization callback binding rejects unsafe schemes, fragments, credentials, whitespace, and non-loopback HTTP hosts.
- Normalized provider errors and provider codes redact common bearer/token/secret/password/cookie forms at the provider boundary, including quoted JSON-like and query-like assignments.
- Operation payloads and durable checkpoints recursively reject credential-shaped keys and cyclic structures before SQLite writes.
- Durable operation intents, checkpoints, retries, and rate-limit waits require JSON-object payloads with string keys before SQLite writes.
- Durable operation JSON rejects non-finite numbers on write and read, and operation/worker identifiers are validated before lease transitions.
- Shared SQLite JSON helpers apply deterministic serialization and reject non-standard numbers in capability and plan payloads as well as operation state.
- Adapter-backed playlist import orchestration that preserves normalized pagination/completeness guarantees.
- Copy plans bind target connection and effective write-capability evidence into their digest.
- Deterministic provider adapter registry with manifest discovery and duplicate-provider protection.
- Concrete provider manifests expose upstream dependencies and a dated research review marker.
- Offline-testable official Spotify playlist reader/writer with bounded pagination, explicit write-capability gating, and normalized error categories.
- Spotify write adapters reject blank playlist/entry identifiers and unknown visibility values before issuing provider requests.
- Explicitly scoped official YouTube Data API video-playlist reader; it is not represented as YouTube Music.
- Experimental official Apple Music library-playlist reader with separate developer/user token inputs.
- Provider readers enforce bounded page sizes, repeated-cursor detection, and configurable maximum page counts.
- Provider readers fail closed on malformed/non-absolute continuation links, backward offsets, and non-textual access/page tokens.
- Experimental Home Assistant App metadata scaffold with Ingress-only management and `/data` persistence.
- Explicit runtime resource composition and reverse-order shutdown for all durable repositories.
- Every SQLite repository enables foreign-key enforcement at connection startup; backup preflight remains a separate integrity check.
- A shared SQLite connection policy applies the same five-second busy timeout and row-factory settings to every durable store.
- Runtime resources support explicit and context-manager lifecycle shutdown.
- Runtime resource shutdown attempts every repository close even if one raises, remains retryable after a partial close, and is idempotent after full closure.
- Partial runtime startup unwinds every repository already opened, retaining the startup exception as primary if cleanup also fails.
- Readiness can validate every composed durable store instead of only the operation queue.
- Runtime resources provide a consistent SQLite online-backup helper while the service remains open.
- Runtime resources can preflight backup integrity and required durable tables read-only before restore design is selected.
- Backup publication validates the temporary SQLite copy before atomically replacing the destination.
- Runtime backups reject missing parent directories and directory destinations before creating a temporary artifact.
- Backup preflight rejects operation databases whose schema version is newer than the running foundation.
- Runtime configuration validates host, port, database path, and Ingress base path before startup.
- Runtime configuration rejects control characters, non-integral ports, and query/fragment-bearing Ingress paths before startup.
- Runtime resources provide a bounded, payload-free aggregate diagnostics view for future authenticated surfaces.
- Runtime readiness validates SQLite integrity, foreign-key references, durable operation state/event values, authorization attempts, provider capability JSON, plan JSON, and resolution payloads; corruption fails closed.
- Provider connection diagnostics expose provider/state and expiry counts, never account or credential data.
- Import diagnostics expose bounded snapshot freshness and availability counts without playlist content.
- Resolution diagnostics expose only manual-decision action counts, never track, actor, or reason data.
- Ingress-relative health/version routing accepts only origin-form request targets, rejects absolute/network-path targets and fragments, and uses normalized traversal-safe base paths.
- The composed runtime HTTP server has an offline route contract and a loopback smoke path for real health/readiness lifecycle checks.
- The current JSON health/readiness/version surface disables caching, MIME sniffing, and referrer propagation.
- The runtime JSON surface rejects non-standard numeric values before writing a response.
- Normalized provider contracts and a dependency-free playlist-page collector proving opaque identity namespaces, completeness, pagination safety, duplicate occurrences, and unavailable-item preservation.
- Normalized provider identity, manifest, capability, entry, and page values reject non-textual or malformed boundary data before it reaches planning.
- Normalized provider pages reject wrong enum/runtime types and duplicate positions before collection; dated manifest evidence must use an ISO date.
- SQLite storage for immutable copy plans, including durable digest-bound acceptance.
- Copy-plan reads and acceptance recompute the digest over execution-relevant content, rejecting tampering even when the stored digest field is unchanged.
- The operation store applies its schema DDL, legacy column migration, and `user_version` marker in one transaction.
- SQLite operation tests exercise real multi-connection races: one operation cannot be claimed twice and concurrent scheduler workers claim distinct queue items.
- Versioned identity assessments and append-only SQLite storage for manual resolution decisions.
- Lossless Unicode-safe identity normalization with explicit version-token and ISRC derived fields; no automatic matching thresholds are assumed.
- An application workflow that persists plans, requires digest acceptance, and enqueues only accepted plans as durable operations.
- A copy executor that creates target playlists through a semantic writer port, checkpoints each occurrence, and reconciles unknown writes before retry.
- SQLite persistence for complete playlist projections that keeps incomplete imports from replacing the last complete snapshot and isolates external IDs by namespace.
- Playlist projections preserve provider object types as part of external identity, including a forward-compatible migration for older rows.
- Playlist projections retain normalized provider titles and source-added timestamps for later explainable identity work.
- Idempotent snapshot publication that rejects reused IDs with different content and never rolls back a newer current pointer.
- An application import use case that reports partial results without advancing freshness or replacing the last complete projection.

## Local container profile

`Dockerfile` packages the dependency-free runtime as a non-root service with the durable volume mounted at `/data`. It is a standalone development/container profile, not yet the published Home Assistant App artifact.

```text
docker build -t symphonia:dev .
docker run --rm -p 8099:8099 -v symphonia-data:/data symphonia:dev
```

The container exposes only the current health/readiness/version surface. A future App manifest must add Ingress, Supervisor metadata, supported architectures, backup declarations, and any direct callback policy only after the runtime SDD blockers are resolved.
- Deterministic `unittest` coverage under `tests/`.
- Static AST boundary tests keep the domain free of adapters/host frameworks and keep the foundation limited to Python's standard library plus local `symphonia` modules.

The package is an implementation foundation, not a claim that the corresponding capability SDDs are complete. Provider OAuth, secret storage, user authentication, Ingress UI, a complete migration ledger beyond the current forward-compatible SQLite path, backup retention/restore policy, and production runtime handler wiring remain unimplemented and blocked by their SDD decisions. The Home Assistant-native UI direction and compatibility-layer boundary are documented in [ADR 0004](../decisions/0004-home-assistant-native-ui.md) and the [UI foundation SDD](../../specs/home-assistant-native-ui.md), but this foundation slice does not authorize or include frontend implementation.

## Local verification

From the repository root:

```text
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The command must run without network access, provider accounts, Home Assistant, or a pre-existing database.

## Boundary rules

- `symphonia.domain` imports no infrastructure, provider, Home Assistant, or web framework modules.
- Application services orchestrate domain values and do not call provider SDKs directly.
- SQLite is an adapter behind the operation repository; it is not exposed as a domain concept.
- The initial Python choice is a reversible implementation baseline, not a final product-stack decision. Any external dependency or deployment commitment requires an SDD/ADR update and tests.
