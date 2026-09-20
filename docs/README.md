# Documentation map

**Status:** baseline for review
**Last reviewed:** 2026-09-20

This documentation is the horizontal implementation contract for Symphonia. It deliberately separates product intent, domain rules, architecture, provider facts, accepted decisions, and unresolved choices. The vertical, capability-level contracts live in the [SDD catalog](../specs/CATALOG.md) and select from these shared rules without overriding them.

## Sources of truth

| Document | Owns | Does not own |
| --- | --- | --- |
| [SDD standard and catalog](../specs/README.md) | Capability boundaries, readiness, end-to-end design, numeric test budgets, acceptance and evidence | Shared product policy or silent overrides of horizontal specifications |
| [Product specification](product/product-specification.md) | Outcomes, scope, journeys, product requirements | Entity design or technology choices |
| [Domain model](domain/domain-model.md) | Ubiquitous language, invariants, identity, copy and sync semantics | Provider API facts |
| [System architecture](architecture/system-architecture.md) | Boundaries, execution model, security and operations | Final implementation stack |
| [Provider specification](providers/provider-specification.md) | Provider port, capabilities, normalized errors | Claims about a specific API |
| [Provider research](providers/provider-research.md) | Dated, sourced facts about provider APIs | Product policy or permanent architecture |
| [Home Assistant music ecosystem review](providers/home-assistant-ecosystem-review.md) | Reusable patterns and cautions from existing HA music projects | Dependency selection or provider guarantees |
| [Development specification](development/development-specification.md) | Specification workflow, testing and delivery gates | Product scope |
| [ADRs](decisions/README.md) | Decisions that have actually been accepted | Proposals and guesses |
| [Open questions](open-questions.md) | Decisions needed, assumptions, risk register, next design work | Accepted requirements |

## Normative language

`MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, and `MAY` are normative. Lowercase uses are explanatory. Each requirement has a stable identifier:

| Prefix | Area |
| --- | --- |
| `SYM-PROD` | Product and user experience |
| `SYM-ACC` | Local and provider accounts |
| `SYM-LIB` | Unified library |
| `SYM-MATCH` | Identity resolution |
| `SYM-PL` | Playlist copy |
| `SYM-SYNC` | Persistent synchronization |
| `SYM-PROV` | Provider abstraction |
| `SYM-ARCH` | Architecture and persistence |
| `SYM-JOB` | Background execution |
| `SYM-SEC` | Security and credentials |
| `SYM-OBS` | Observability |
| `SYM-HA` | Home Assistant |
| `SYM-TEST` | Testing |
| `SYM-DEP` | Deployment |

Requirement identifiers are never reused. Removed requirements remain in history and should be marked superseded rather than silently renumbered.

## Status model

- **Accepted**: an explicit product constraint or recorded ADR; implementation may rely on it.
- **Proposed**: a reviewable direction; implementation must not treat it as settled.
- **Open**: a choice or fact still requiring evidence or owner input.
- **Research snapshot**: a dated external fact that must be revalidated before implementation.

The current baseline is documentation for review, not approval to implement. The repository must remain free of production application code until the owner explicitly approves implementation.

## Change workflow

1. Link a change to one or more requirement identifiers.
2. Select or create the capability SDD from the [catalog](../specs/CATALOG.md); use the [mandatory template](../specs/_template.md).
3. Update product/domain specifications before or with the SDD when shared behavior changes.
4. Record a durable, consequential decision as an ADR; do not use ADRs for routine coding choices.
5. Keep provider facts in dated research and link to official sources.
6. Move answered questions into requirements or ADRs and leave a pointer to the resolution.
7. Do not implement until the SDD passes its readiness gate and the owner explicitly approves implementation.
8. Add acceptance tests traceable to the affected requirements and update catalog evidence with the implementation.
