# Development and verification specification

**Status:** proposed baseline
**Last reviewed:** 2026-09-20

## Specification-driven workflow

Implementation begins only when the applicable capability SDD is `Ready for implementation` and the owner explicitly approves the increment. The SDD lifecycle, required content, readiness gate, and catalog rules are defined in the [SDD standard](../../specs/README.md). Start new capability designs from the [mandatory template](../../specs/_template.md), and keep their state in the [catalog](../../specs/CATALOG.md).

For each proposed increment:

1. Identify product outcomes and requirement IDs.
2. Resolve any open decision that changes externally observable behavior.
3. Write or update the cataloged SDD, including examples, denial/error behavior, provider capability needs, and a numeric risk-derived test budget.
4. Add or revise an ADR only for a durable consequential decision.
5. Define acceptance tests and fixture data before production code.
6. Review the SDD against every readiness gate and obtain explicit owner approval.
7. Implement inward-facing domain/application behavior first, then adapters/presentation.
8. Run focused tests, the complete local suite, packaging checks, and secret scans.
9. Review the final diff for requirement, SDD, catalog evidence, documentation, migration, and diagnostics consistency.

Product requirements say **what** must happen; domain documents define terms/invariants; ADRs say **why** a durable choice was made; an SDD says **how** one vertical capability will behave, fail, recover, be verified, and become ready to ship.

## SDD content

The complete required structure lives in [`specs/_template.md`](../../specs/_template.md). At minimum, every material SDD contains:

- status, owner, date, and related requirement IDs;
- user outcome and explicit non-goals;
- preconditions and required connection capabilities;
- normal, empty, ambiguous, partial, denial, timeout, restart, and cancellation examples;
- state transitions and transaction/idempotency boundaries;
- security/privacy and provider-policy implications;
- observable events, metrics, history, and user-facing errors;
- migration/rollback impact;
- a numeric, risk-derived automated test budget and acceptance scenarios; and
- unresolved questions clearly separated from decisions.

Small implementation changes may update an existing SDD instead of creating one. They may not bypass the applicable contract, weaken its verification budget silently, or use code as the only record of a product or architectural decision.

## Test strategy

### Domain unit and property tests

Fast, deterministic tests cover invariants without database, network, clock, environment, Home Assistant, or provider SDKs.

Examples:

- a provider ID never becomes a recording ID;
- order and duplicate occurrences survive playlist transformations;
- a manual rejection prevents automatic relinking;
- plan digests change when inputs/capabilities/policy change;
- job and operation state transitions reject impossible moves;
- matching normalization is Unicode-safe and retains originals; and
- retries never convert an unknown write into a blind duplicate write.

Property/generative tests SHOULD cover ordered-list diffs, duplicates, batching boundaries, Unicode metadata, duration tolerances, and replay/idempotency.

### Application/use-case tests

Use in-memory deterministic ports for providers, repositories, jobs, clock, identifiers, and secret references. Cover every user journey and denial/partial path. Tests assert domain outcomes and port interactions, not framework internals.

### Provider contract tests

One shared suite runs against every adapter's offline fake/fixture implementation and concrete mapping layer. It verifies:

- pagination and no silent truncation;
- media/unavailable/unknown-type handling;
- adapter-manifest classification plus adapter-, connection-, object-, and health-level capability behavior;
- colliding upstream IDs across provider instances and media types;
- normalized errors and retry advice;
- batch/order/duplicate behavior;
- timeout/cancellation;
- secret-safe exceptions/logs; and
- reconciliation after a simulated lost write response.

Fixtures MUST be synthetic or legally redistributable, minimal, versioned, and free of real tokens/account identifiers. Raw captured payloads require sanitization and policy review before commit.

### Persistence and migration tests

Run against the real selected database engine. Cover transactions, constraints, lease contention, restart recovery, consistent backup, restore, retention cleanup, and migrations from every supported release fixture. Migration tests must include failure/interruption behavior.

### Job/fault tests

Use a controlled clock and fault-injecting providers to test 429/reset, timeouts before/after writes, 401 refresh races, 403, 404, 5xx, malformed payloads, truncated pagination, process termination at each checkpoint, stale leases, cancellation, and provider revision conflicts.

### HTTP/UI tests

Contract tests validate request/response schemas, authentication, authorization, pagination, base paths, correlation, and sanitized errors. Browser tests cover Ingress-relative navigation, narrow/wide layouts, keyboard access, focus/error announcements, OAuth return/error screens, ambiguous-resolution review, copy preview, partial results, reconnect, and restart recovery.

UI tests MUST not consider an element visible or a request successful proof that the domain outcome occurred; they verify the returned operation and history.

### Home Assistant App tests

Artifact tests inspect repository/App metadata, supported architectures, pinned image inputs, Ingress configuration, startup, persistent `/data`, backup settings, non-root execution, mapped folders, exposed ports, least privileges, health, and version consistency. A fake Supervisor/Ingress boundary should exercise path rewriting and trusted-header isolation. If a direct callback listener exists, tests must prove that its management and internal API routes are unreachable.

At least one disposable Home Assistant OS/Supervised-compatible smoke path must verify install/start/Ingress/restart/backup-restore before stable release. The exact CI environment is an implementation decision.

### Standalone tests

If/when shipped, start the published immutable image with a fresh volume and explicit authentication, then verify migration, health/readiness, provider fake workflow, restart persistence, backup/restore, and private-by-default network configuration.

### Live-provider smoke tests

Live tests are opt-in and never part of the ordinary suite. They use dedicated accounts, unique prefixed playlists, bounded item counts, conservative quotas, and cleanup that reports rather than hides failure. Destructive cleanup targets only IDs created by that run. Credentials live only in an approved secret facility.

The live matrix must verify documented behavior, not reverse-engineered endpoints unless a separately accepted unofficial adapter exists.

## Test requirements

- **SYM-TEST-001:** Every normative requirement implemented MUST be traceable to at least one automated test or an explicitly documented manual/platform verification.
- **SYM-TEST-002:** Domain and application test suites MUST run without network, provider accounts, Home Assistant, or wall-clock timing.
- **SYM-TEST-003:** Every provider adapter MUST pass the common offline contract suite.
- **SYM-TEST-004:** Provider write workflows MUST test success, rate limit, auth expiry, permanent rejection, partial batch, timeout before write, unknown outcome after write, reconciliation, and restart.
- **SYM-TEST-005:** Secret-canary values MUST be asserted absent from logs, exceptions, API responses, metrics labels, traces, diagnostics, database non-secret fields, and UI snapshots.
- **SYM-TEST-006:** Tests MUST cover duplicated playlist entries, unavailable/deleted items, non-music media, empty playlists, maximum batch boundaries, and source change after planning.
- **SYM-TEST-007:** Matching evaluation MUST use a reviewed corpus containing covers, live/studio, remaster, remix/edit, acoustic, clean/explicit, featured-artist, compilation, localization, and misleading-title cases.
- **SYM-TEST-008:** Resolver changes MUST report corpus regressions by category and MUST NOT silently overwrite manual decisions.
- **SYM-TEST-009:** App packaging and Ingress-relative routing MUST be release-gated.
- **SYM-TEST-010:** Tests that touch external providers MUST be explicitly selected, quota-bounded, and safe to re-run.
- **SYM-TEST-011:** Provider tests MUST cover object-level capability denial and identical upstream IDs from different media types or provider instances without collision.
- **SYM-TEST-012:** App artifact/smoke tests MUST enumerate every listening port and prove that any non-Ingress callback listener cannot reach management routes or trust Ingress identity headers.
- **SYM-TEST-013:** Migration tests MUST use a per-release history, include stable/beta path divergence, and prove failure leaves the prior database recoverable rather than replacing locally authored state with a fresh rescan.

## Matching evaluation

Before accepting automatic-match thresholds, create a small human-labeled corpus whose licenses/terms permit the stored fields. Separate candidate-retrieval recall from link precision. False-positive links are generally more harmful than unmatched items because they silently copy the wrong recording, so metrics and review must report both.

Do not train an ML model on Spotify content; Spotify's current search documentation explicitly prohibits using Spotify content to train machine-learning/AI models. “Learning” in the MVP means deterministic persistence and reuse of user mappings.

Numeric acceptance thresholds are open until the corpus and error costs are reviewed.

## Quality gates

A change is incomplete until, in proportion to its scope:

- specifications and requirement traceability agree with behavior;
- tests cover success, denial, error, partial, and restart paths;
- provider calls have timeouts, rate-limit handling, and sanitized errors;
- no secret or real private identifier is present in source/fixtures/output;
- migrations, backup, and rollback implications are documented and tested;
- frontend accessibility and Ingress base-path behavior pass;
- App/standalone artifact metadata is consistent;
- local checks and CI pass; and
- the full diff contains no unrelated generated artifacts.

## Deployment and release expectations

- **SYM-DEP-001:** The primary release MUST provide a Home Assistant App repository, immutable versioned images, checksums/signing where the selected publication workflow supports it, and upgrade notes.
- **SYM-DEP-002:** The App MUST persist only documented runtime state under `/data` and MUST start successfully after restore without performing provider writes until migrations/recovery complete.
- **SYM-DEP-003:** A release MUST document supported Home Assistant versions and CPU architectures.
- **SYM-DEP-004:** Configuration validation MUST fail closed with actionable messages before workers start.
- **SYM-DEP-005:** The deployment MUST provide health, readiness, version, and sanitized diagnostics.
- **SYM-DEP-006:** Backup and restore documentation MUST cover the database, encryption-key material, provider reauthorization consequences, and active jobs.
- **SYM-DEP-007:** Updates MUST be reversible via documented backup/restore or compatible downgrade policy; unsupported downgrade MUST be detected, not attempted.
- **SYM-DEP-008:** The service MUST handle graceful shutdown by stopping new work, checkpointing or abandoning leases safely, and bounding shutdown time.
- **SYM-DEP-009:** Default App permissions and network exposure MUST be minimal; Docker socket, host network, SSH, arbitrary host filesystem, and privileged mode are prohibited unless a future ADR proves necessity.
- **SYM-DEP-010:** Standalone mode, if released, MUST use the same domain/application code and migration format as the Home Assistant App.

Release channels, semantic-version policy, supported upgrade window, and exact artifact tooling remain open implementation decisions.

## Initial traceability examples

| Requirement | Planned verification |
| --- | --- |
| `SYM-MATCH-006` manual reuse | Domain unit + application workflow + resolver corpus regression test |
| `SYM-PL-005` order/duplicates | Property test + both provider contract suites + live smoke |
| `SYM-PL-006` idempotency | Fault-injected unknown-write/reconciliation/restart test |
| `SYM-PROV-004` pagination | Shared adapter contract at zero, one, boundary, and multi-page counts |
| `SYM-PROV-018` external identity scope | Contract fixtures with cross-type and cross-instance ID collisions |
| `SYM-JOB-004` durable retry | Database/controlled-clock restart test |
| `SYM-SEC-004` secret safety | Canary scan across all output boundaries |
| `SYM-SEC-009` callback isolation | Listener route enumeration + Home Assistant App smoke test |
| `SYM-SEC-010` untrusted provider values | Path/URI/redirect/egress injection tests |
| `SYM-HA-002` Ingress | Base-path HTTP/browser + App smoke test |
| `SYM-DEP-006` restore | Artifact smoke using a backup with active/waiting jobs |

The SDD catalog and each capability's traceability section are the prospective matrix before code exists. Implementation evidence should be generated or maintained when work is approved; this baseline does not invent test filenames before a stack exists.
