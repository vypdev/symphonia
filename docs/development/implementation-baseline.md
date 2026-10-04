# Implementation baseline

**Status:** owner-approved foundation slice
**Last reviewed:** 2026-09-27

The first implementation increment is intentionally narrower than any provider or Home Assistant capability. It proves the provider-independent core and the durable-operation persistence contract without selecting an external web framework, provider SDK, OAuth strategy, or frontend stack.

## Current slice

- Python 3.11+ package under `src/symphonia`.
- Dependency-free domain values for ordered playlist snapshots, the six product entry classifications, copy policies, immutable copy plans, and acceptance digests.
- Dependency-free SQLite operation repository proving idempotent creation, time-bounded worker leases, checkpoint ownership, retry scheduling, and expired-lease recovery.
- Atomic scheduler-facing claim selection for queued, due-retry, and expired-lease operations.
- Append-only SQLite operation event history for auditable transitions with sanitized checkpoint summaries.
- Bounded redacted operation diagnostics for support and a future authenticated operations view, with hard item/event caps.
- Diagnostic operation/event limits require bounded positive integers and reject booleans and fractional values.
- Diagnostic payload/checkpoint key lists are capped at 100 entries and mark truncation.
- Diagnostic key summaries select their bounded sorted window without sorting/materializing the complete key set.
- Diagnostic event queries fetch only the requested window plus one row to determine truncation.
- Bounded recent-operation diagnostics listing that exposes only redacted support views.
- Aggregate operation queue summaries expose state counts, eligible age, and expired leases without payload data.
- Explicit provider rate-limit waits with absolute retry times and durable eligibility.
- Bounded transient retry budgets for copy and import handlers with durable exhaustion outcomes.
- Lease renewal refuses cancellation-requested work; copy and import executors checkpoint a cooperative stop before beginning their next provider step when they still hold a valid lease.
- Lease-expiry recovery is audited distinctly from first claims, with prior worker identity retained only as metadata.
- An expired lease with cancellation requested is quarantined in `waiting_user` with durable reconciliation evidence, never sent through the ordinary handler, and can be finalized only through an explicit no-effect/effect-confirmed repository resolution; checkpoint, retry, and rate-limit release paths preserve this quarantine; authenticated caller wiring remains out of scope.
- Recovery tests cover unknown cancelled writes across checkpoint, retry, rate-limit, and expired-lease paths; ordinary resume is refused until explicit no-effect or effect-confirmed resolution.
- Redacted operation diagnostics expose a bounded unknown-step indicator and only allowlisted reconciliation/recovery outcome metadata, never unknown step IDs or checkpoint values.
- Provider connection persistence with account uniqueness, opaque secret references, health states, and effective capability evidence.
- Application connection service for verified-account registration, capability probes, degraded health, and reauthorization-required classification.
- Application-owned attempt, connection, and operation repository protocols keep current use cases independent of SQLite imports; a package-wide AST test enforces the boundary.
- The SQLite operation adapter keeps one lock-protected public facade; separate claim, transition, and scheduling modules each finish a transaction before returning. Shared context, schema, validation, and rollback modules keep persistence concerns within infrastructure without exposing SQLite to application code.
- Pure capability-layer intersection and requirement checks for adapter/connection/object/health constraints.
- Durable operation runner that atomically claims eligible work and fails unwired operation types before side effects.
- The operation runner validates handler result type and identity, then returns the current persisted record rather than trusting a potentially stale handler object.
- Cooperative single-process operation worker with interruptible polling and injected clock support.
- Copy executor can run as a claimed operation handler, preserving the same restart/checkpoint semantics under the runner.
- Copy execution durably marks a target-create or entry-add step in-flight before the provider call; a resumed step is reconciled before any repeated mutation, and inconclusive evidence or reconciliation errors stay in `waiting_user`. The current boolean entry-reconciliation port treats `false` only as inconclusive and cannot represent proven no-effect; a richer provider contract and the full copy capability remain blocked in the Draft SDD.
- Copy execution retains permanently failed occurrences as itemized issues across waits and restarts; resuming a later uncertain write does not repeat those failed writes.
- Before resumed writes, pure copy-progress validation rejects malformed, duplicated, out-of-plan, gapped, out-of-order, or contradictory item progress and invalid target identifiers into `waiting_user` for review. Confirmed and permanently failed occurrences must form an uninterrupted prefix of the accepted writable plan.
- Playlist import executor persists intent before reads and reports succeeded, partial, waiting-user, retry, and rate-limit outcomes durably. Current scope is one playlist: pages are materialized in memory, and transient retries re-read from the beginning because page-level durable staging/checkpoints are not implemented; full library-import behavior remains blocked in its Draft SDD.
- Resumed playlist imports reject non-textual stored playlist identifiers and conflicting provider bindings before any adapter read; malformed intent is not coerced into a new external identity.
- Provider-neutral authorization attempts with hashed state, exact redirect binding, expiry, and single-use consumption.
- Direct-callback authorization can resolve a durable attempt by the returned state digest after restart without persisting raw state; ambiguous digests fail closed.
- Authorization consumption is covered across independent SQLite connections so callback replay races produce exactly one consumed attempt.
- Authorization state is bounded before hashing, required identifiers are validated before SQLite writes, and durable failure codes use a bounded safe alphabet.
- Application authorization boundary that generates one-use state without persisting the raw value.
- Authorization callback binding rejects unsafe schemes, fragments, credentials, whitespace, and non-loopback HTTP hosts.
- Normalized provider errors and provider codes redact common bearer/token/secret/password/cookie forms at the provider boundary, including quoted JSON-like and query-like assignments.
- Operation payloads and durable checkpoints recursively reject credential-shaped keys and cyclic structures before SQLite writes.
- Durable operation intents, checkpoints, retries, rate-limit waits, and audit events require JSON-object payloads with string keys and reject token-, password-, authorization-, and API-key-shaped fields in snake, kebab, and camel case on writes and reads, without echoing rejected key names in errors.
- Durable operation JSON rejects non-finite numbers on write and read, and repository entrypoints validate operation/worker identifiers before reads and state transitions.
- Checkpoint transitions reject non-string and unknown state values before opening a transaction.
- Operation and audit-event timestamps must have a defined UTC offset on write and read; the repository never interprets naive timestamps using the host's local zone.
- Lease durations passed to the durable operation repository must be positive integers; booleans and lossy/coercible values are rejected consistently with the worker boundary.
- Shared SQLite JSON helpers apply deterministic serialization and reject non-standard numbers in capability and plan payloads as well as operation state.
- Adapter-backed playlist import orchestration that preserves normalized pagination/completeness guarantees.
- Copy plans bind target connection and effective write-capability evidence into their digest.
- Deterministic provider adapter registry with manifest discovery and duplicate-provider protection.
- Concrete provider manifests expose upstream dependencies and a dated research review marker.
- Offline-testable official Spotify playlist reader/writer with bounded pagination, explicit write-capability gating, and normalized error categories.
- Spotify and YouTube Data share a provider-neutral JSON transport; the YouTube adapter no longer imports the Spotify adapter, and default transport errors identify the correct provider without echoing tokens.
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
- Runtime resource shutdown attempts every repository close even if one raises or is interrupted, remains retryable after a partial close, and is idempotent after full closure.
- Partial runtime startup unwinds every repository already opened, including on interruption, retaining the startup exception as primary if cleanup also fails.
- HTTP server construction closes composed resources on any startup failure without replacing the original cause with a cleanup error.
- The CLI treats `SIGTERM` as a graceful stop and closes the HTTP listener and composed resources before restoring the prior signal handler.
- Offline CLI lifecycle tests cover graceful stop, startup failure, listener-close failure, and invalid configuration before resources open.
- Every SQLite store closes its newly opened connection when schema initialization fails, preserving the migration error as primary.
- Readiness can validate every composed durable store instead of only the operation queue.
- Runtime resources request a consistent online backup through the operation repository adapter while the service remains open, without reaching into its private connection.
- Runtime resources can preflight backup integrity and required durable tables read-only before restore design is selected.
- Backup publication validates the temporary SQLite copy before atomically replacing the destination.
- Failed backup cleanup preserves the primary backup error and annotates a secondary temporary-file removal failure.
- Runtime backups reject missing parent directories, directory destinations, and final-component symlinks before creating a temporary artifact.
- Backup preflight rejects operation databases whose schema version is newer than the running foundation.
- Runtime configuration and the public server factory validate host, port, database path, and Ingress base path before opening stores or binding a socket; direct resource opening shares the database-path validator, including consistent `~` expansion for SQLite and backup path comparisons.
- Port parsing accepts integer values, numeric strings, and integral floats while rejecting booleans and arbitrary integer-coercible objects that could silently truncate.
- Runtime host, database, and Ingress values reject Unicode C0/C1 control characters before host whitespace normalization; the shared Ingress normalizer also rejects query/fragments, backslashes, repeated slashes, and literal dot segments.
- Runtime resources provide a bounded, payload-free aggregate diagnostics view for future authenticated surfaces.
- Runtime readiness validates SQLite integrity, foreign-key references, durable operation state/event values, authorization attempts, provider capability JSON, plan JSON, and resolution payloads; malformed, out-of-range, or excessively nested durable values fail closed.
- Durable operation readiness validates operation and event rows incrementally instead of materializing the full ledger in memory.
- Provider connection diagnostics expose provider/state and expiry counts, never account or credential data.
- Import diagnostics expose bounded snapshot freshness and availability counts without playlist content.
- Resolution diagnostics expose only manual-decision action counts, never track, actor, or reason data.
- Ingress-relative health/version routing accepts only origin-form request targets, rejects absolute/network-path targets and fragments, and uses normalized traversal-safe base paths.
- The synchronous health server caps each accepted connection at a two-second socket timeout so an incomplete client cannot hold the only request loop indefinitely.
- The composed runtime HTTP server has an offline route contract and a loopback smoke path for real health/readiness lifecycle checks.
- The current JSON health/readiness/version surface disables caching, MIME sniffing, and referrer propagation.
- The HTTP handler suppresses the Python version header and returns generic JSON for parser/method errors, closing the connection without reflecting details.
- Client disconnects or response-write timeouts close the request quietly instead of emitting a server traceback.
- The container health probe follows the configured runtime port and Ingress base path.
- The container health probe follows the normalized configured listener host, mapping IPv4/IPv6 wildcard binds to their loopback equivalents, and requires the Symphonia ready JSON contract rather than any HTTP 200 response.
- The runtime JSON surface rejects non-standard numeric values before writing a response.
- Normalized provider contracts and a dependency-free playlist-page collector proving opaque identity namespaces, completeness, pagination safety, duplicate occurrences, and unavailable-item preservation.
- Normalized provider identity, manifest, capability, entry, and page values reject non-textual or malformed boundary data before it reaches planning.
- Normalized provider pages reject wrong enum/runtime types and duplicate positions before collection; dated manifest evidence must use an ISO date.
- SQLite storage for immutable copy plans, including durable digest-bound acceptance.
- Copy planning and execution take an application plan repository port and a domain-owned accepted-plan record; SQLite keeps its previous `StoredCopyPlan` export as an alias for foundation callers.
- Copy-plan reads and acceptance recompute the digest over execution-relevant content, rejecting tampering even when the stored digest field is unchanged.
- The operation store applies its schema DDL, legacy column migration, and `user_version` marker in one transaction.
- Operation-store transactions include transaction start in their protected scope, roll back on process-level interruptions when possible, and preserve the primary error if rollback also fails.
- The durable operation repository serializes complete calls on its shared SQLite connection; cross-connection and cross-process correctness remains enforced by SQLite transactions and leases.
- SQLite operation tests exercise real multi-connection races: one operation cannot be claimed twice and concurrent scheduler workers claim distinct queue items.
- Versioned identity assessments and append-only SQLite storage for manual resolution decisions.
- Lossless Unicode-safe identity normalization with explicit version-token and ISRC derived fields; no automatic matching thresholds are assumed.
- An application workflow that persists plans, requires digest acceptance, and enqueues only accepted plans as durable operations.
- A copy executor whose target and entry stages share an explicit run context, create target playlists through a semantic writer port, checkpoint each occurrence, and reconcile unknown writes before retry.
- SQLite persistence for complete playlist projections that keeps incomplete imports from replacing the last complete snapshot and isolates external IDs by namespace.
- The playlist import use case depends on an application projection port and returns a domain-owned published snapshot value; SQLite remains the adapter, and its prior `StoredPlaylistSnapshot` import is retained as an alias for foundation callers.
- Playlist projections preserve provider object types as part of external identity, including a forward-compatible migration for older rows.
- Playlist projections retain normalized provider titles and source-added timestamps for later explainable identity work.
- Idempotent snapshot publication that rejects reused IDs with different content and never rolls back a newer current pointer.
- An application import use case that reports partial results without advancing freshness or replacing the last complete projection.

## Local container profile

`Dockerfile` packages the dependency-free runtime with persistent `/data`. Supervisor mounts that directory as root: the container entrypoint briefly adjusts only the directory and known SQLite files, then drops supplementary groups, GID, and UID before executing the service as `symphonia`. The first real [local Supervisor/App smoke](ha-app-lab.md) found and fixed this mount-ownership failure. The profile is not yet a published Home Assistant App artifact.

```text
docker build -t symphonia:dev .
docker run --rm -p 8099:8099 -v symphonia-data:/data symphonia:dev
```

The container exposes health/readiness/version plus the separately scoped [operational dashboard](../../specs/operational-dashboard.md). Experimental App metadata enables an administrator-only Ingress panel and two build architectures. A local [Core-to-Supervisor smoke](ha-app-lab.md) verifies session enforcement, health/readiness, root, built JS, and live redacted dashboard API routing through Ingress; the authenticated in-app browser renders and refreshes that first view. A supported platform matrix, backup/restore declarations, and any direct callback policy remain behind the runtime and broader UI SDD gates.
- Runtime composition closes partially opened stores in reverse order. Failure-injection tests verify cleanup continues after a close error and preserves the original startup failure.
- Deterministic `unittest` coverage under `tests/`.
- Static AST boundary tests keep the domain free of adapters/host frameworks and keep the foundation limited to Python's standard library plus local `symphonia` modules.

The package is an implementation foundation, not a claim that the corresponding capability SDDs are complete. Provider OAuth, secret storage, user authentication beyond Supervisor's Ingress session, the full feature UI, a complete migration ledger beyond the current forward-compatible SQLite path, backup retention/restore policy, and full production lifecycle remain blocked by their SDD decisions. The first read-only operational dashboard has its own ready contract and owner approval. The broader Home Assistant-native UI direction and compatibility-layer boundary remain documented in [ADR 0004](../decisions/0004-home-assistant-native-ui.md) and the [UI foundation SDD](../../specs/home-assistant-native-ui.md).

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
