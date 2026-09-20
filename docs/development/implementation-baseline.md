# Implementation baseline

**Status:** owner-approved foundation slice
**Last reviewed:** 2026-09-20

The first implementation increment is intentionally narrower than any provider or Home Assistant capability. It proves the provider-independent core and the durable-operation persistence contract without selecting an external web framework, provider SDK, OAuth strategy, or frontend stack.

## Current slice

- Python 3.11+ package under `src/symphonia`.
- Dependency-free domain values for ordered playlist snapshots, the six product entry classifications, copy policies, immutable copy plans, and acceptance digests.
- Dependency-free SQLite operation repository proving idempotent creation, time-bounded worker leases, checkpoint ownership, retry scheduling, and expired-lease recovery.
- Normalized provider contracts and a dependency-free playlist-page collector proving opaque identity namespaces, completeness, pagination safety, duplicate occurrences, and unavailable-item preservation.
- SQLite storage for immutable copy plans, including durable digest-bound acceptance.
- Versioned identity assessments and append-only SQLite storage for manual resolution decisions.
- An application workflow that persists plans, requires digest acceptance, and enqueues only accepted plans as durable operations.
- Deterministic `unittest` coverage under `tests/`.

The package is an implementation foundation, not a claim that the corresponding capability SDDs are complete. Provider OAuth, provider API adapters, user authentication, Ingress, UI, migrations beyond the initial schema, backup/restore, and operation handlers remain unimplemented and blocked by their SDD decisions.

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
