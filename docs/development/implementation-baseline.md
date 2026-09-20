# Implementation baseline

**Status:** owner-approved foundation slice
**Last reviewed:** 2026-09-20

The first implementation increment is intentionally narrower than any provider or Home Assistant capability. It proves the provider-independent core and the durable-operation persistence contract without selecting an external web framework, provider SDK, OAuth strategy, or frontend stack.

## Current slice

- Python 3.11+ package under `src/symphonia`.
- Dependency-free domain values for ordered playlist snapshots, the six product entry classifications, copy policies, immutable copy plans, and acceptance digests.
- Dependency-free SQLite operation repository proving idempotent creation, time-bounded worker leases, checkpoint ownership, retry scheduling, and expired-lease recovery.
- Atomic scheduler-facing claim selection for queued, due-retry, and expired-lease operations.
- Append-only SQLite operation event history for auditable transitions with sanitized checkpoint summaries.
- Bounded redacted operation diagnostics for support and a future authenticated operations view.
- Explicit provider rate-limit waits with absolute retry times and durable eligibility.
- Bounded transient retry budgets for copy and import handlers with durable exhaustion outcomes.
- Provider connection persistence with account uniqueness, opaque secret references, health states, and effective capability evidence.
- Application connection service for verified-account registration, capability probes, degraded health, and reauthorization-required classification.
- Pure capability-layer intersection and requirement checks for adapter/connection/object/health constraints.
- Durable operation runner that atomically claims eligible work and fails unwired operation types before side effects.
- Cooperative single-process operation worker with interruptible polling and injected clock support.
- Copy executor can run as a claimed operation handler, preserving the same restart/checkpoint semantics under the runner.
- Playlist import executor persists intent before reads and reports succeeded, partial, waiting-user, retry, and rate-limit outcomes durably.
- Provider-neutral authorization attempts with hashed state, exact redirect binding, expiry, and single-use consumption.
- Application authorization boundary that generates one-use state without persisting the raw value.
- Adapter-backed playlist import orchestration that preserves normalized pagination/completeness guarantees.
- Copy plans bind target connection and effective write-capability evidence into their digest.
- Deterministic provider adapter registry with manifest discovery and duplicate-provider protection.
- Offline-testable official Spotify playlist reader/writer with bounded pagination, explicit write-capability gating, and normalized error categories.
- Explicitly scoped official YouTube Data API video-playlist reader; it is not represented as YouTube Music.
- Experimental official Apple Music library-playlist reader with separate developer/user token inputs.
- Experimental Home Assistant App metadata scaffold with Ingress-only management and `/data` persistence.
- Explicit runtime resource composition and reverse-order shutdown for all durable repositories.
- Ingress-relative health/version routing with normalized, traversal-safe base paths.
- Normalized provider contracts and a dependency-free playlist-page collector proving opaque identity namespaces, completeness, pagination safety, duplicate occurrences, and unavailable-item preservation.
- SQLite storage for immutable copy plans, including durable digest-bound acceptance.
- Versioned identity assessments and append-only SQLite storage for manual resolution decisions.
- Lossless Unicode-safe identity normalization with explicit version-token and ISRC derived fields; no automatic matching thresholds are assumed.
- An application workflow that persists plans, requires digest acceptance, and enqueues only accepted plans as durable operations.
- A copy executor that creates target playlists through a semantic writer port, checkpoints each occurrence, and reconciles unknown writes before retry.
- SQLite persistence for complete playlist projections that keeps incomplete imports from replacing the last complete snapshot and isolates external IDs by namespace.
- Playlist projections preserve provider object types as part of external identity, including a forward-compatible migration for older rows.
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

The package is an implementation foundation, not a claim that the corresponding capability SDDs are complete. Provider OAuth, secret storage, user authentication, Ingress UI, a complete migration ledger beyond the current forward-compatible SQLite path, backup/restore, and production runtime handler wiring remain unimplemented and blocked by their SDD decisions.

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
