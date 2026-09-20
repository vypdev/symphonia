# Software Design Document standard

This directory contains Symphonia's implementation-driving Software Design Documents (SDDs). An SDD is a vertical contract for one product capability: it joins product behavior, domain rules, architecture, provider boundaries, user experience, failure recovery, security, testing, documentation, and acceptance.

Start new SDDs from [`_template.md`](./_template.md). The capability inventory and readiness state live in [`catalog.json`](./catalog.json); [`CATALOG.md`](./CATALOG.md) is its human-readable companion.

## Relationship to the shared specifications

The existing `docs/` documents remain the horizontal sources of truth:

| Source | Owns |
| --- | --- |
| [`docs/product/product-specification.md`](../docs/product/product-specification.md) | Product scope, journeys, and stable requirement IDs |
| [`docs/product/home-assistant-ui-specification.md`](../docs/product/home-assistant-ui-specification.md) | Cross-cutting UI/component, host-context, accessibility, responsive, and visual compatibility requirements |
| [`docs/domain/domain-model.md`](../docs/domain/domain-model.md) | Shared language, identity, invariants, copy/sync semantics |
| [`docs/architecture/system-architecture.md`](../docs/architecture/system-architecture.md) | System-wide boundaries, security, persistence, and operations |
| [`docs/providers/provider-specification.md`](../docs/providers/provider-specification.md) | Provider port and capability contract |
| [`docs/providers/provider-research.md`](../docs/providers/provider-research.md) | Dated official API evidence |
| [`docs/providers/home-assistant-ecosystem-review.md`](../docs/providers/home-assistant-ecosystem-review.md) | Dated implementation patterns and cautions |
| [`docs/decisions/README.md`](../docs/decisions/README.md) | Accepted architectural decisions |
| [`docs/open-questions.md`](../docs/open-questions.md) | Unresolved owner choices and research gates |

An SDD does not duplicate or quietly override those sources. It selects the applicable requirements and makes them implementable end to end. If an SDD discovers a missing or conflicting global rule, update the owning document or record an ADR before marking the SDD ready.

## Status model

| Status | Meaning | Implementation consequence |
| --- | --- | --- |
| `Draft` | The capability boundary is useful, but evidence or decisions remain open | No production implementation |
| `Ready for review` | The contract is complete enough for owner and specialist review | No production implementation |
| `Ready for implementation` | Blocking decisions are resolved and all readiness gates pass | Implementation may begin only after explicit owner approval |
| `Implemented` | Code, tests, documentation, migrations, and evidence satisfy the SDD | Changes must update all evidence together |
| `Superseded` | A newer SDD or decision replaces this contract | No new work should target it |

The initial Symphonia SDDs are prospective drafts. There is no implemented behavior to describe as an as-built baseline.

## Required contract

Every SDD MUST cover these concerns or state why a concern is not applicable:

| Concern | Required outcome |
| --- | --- |
| Decision metadata | Status, date, owner, scope, review gates, blockers |
| Problem and evidence | Affected actor, current absence/behavior, primary sources, unknowns |
| Goals and limits | Outcomes, non-goals, fixed safety and product invariants |
| Product journey | Entrypoints, visible surfaces, normal and alternative flows |
| Domain/state model | Shared terms, ownership of facts, states, transitions, invariants |
| Configuration | Safe defaults, bounded alternatives, validation, precedence, persistence, migration |
| Architecture | Dependency direction, pure policy, use cases, ports, adapters, trust/state boundaries |
| UI/UX | Information hierarchy and concrete pending/action/partial/failure/completed examples |
| Failure and recovery | Retained facts, retryability, idempotency, cleanup, operator/user action |
| Security/privacy | Authorization, secrets, untrusted input, abuse/replay, data lifecycle |
| Observability | User status, logs/metrics, correlation, rate-limit and noise behavior |
| Compatibility/rollout | Existing data/jobs, migration, upgrade, rollback, irreversible effects |
| Testing | Numeric risk-derived budget and deterministic evidence |
| Documentation | User, setup, operator, recovery, architecture, and discoverability artifacts |
| Acceptance/DoD | Observable scenarios, requirement traceability, implementation order, gates |

## Authoring rules

- Use the existing `SYM-*` requirement IDs. A new normative rule needs an ID in the horizontal document that owns it before the SDD becomes ready.
- Distinguish accepted facts, proposed defaults, configurable alternatives, fixed limits, and open decisions.
- Use diagrams only when they clarify a multi-step flow, state machine, trust boundary, or dependency graph. Every diagram requires a nearby textual equivalent.
- A `MUST` needs an acceptance scenario and planned verification. A `SHOULD` needs a documented exception rule.
- Provider names belong in adapters and evidence, not in provider-independent policy branches.
- Live provider tests supplement but never replace deterministic offline contract tests.
- Partial success and unknown external write outcomes are first-class states, not generic failures.
- User-facing errors follow: impact, cause, next action, retained state.
- Configuration cannot weaken authorization, secret handling, auditability, identity provenance, or idempotency safeguards.
- Every web-surface SDD maps its feature-specific states and actions onto the Home Assistant-native UI foundation; it does not create a parallel design system or depend on private Home Assistant frontend modules.

## Numeric test budget

Each implementation-driving SDD defines a minimum number of distinct cases distributed across its real risks. The number is a floor, not a substitute for covering every requirement.

Budgets should cover, where applicable:

- pure domain/configuration/planning;
- state transitions, concurrency, replay, cancellation, and unknown outcomes;
- application use cases;
- provider/App/persistence adapters and error mapping;
- HTTP/UI/accessibility/sanitization;
- integration, migration, backup/restore, and security abuse cases.

Parameterized cases count separately only when they represent distinct behavior. No test budget may require live provider calls in the ordinary suite.

## Readiness gate

Before changing an SDD to `Ready for implementation`, reviewers must be able to answer yes:

- Is the user outcome understandable without reading code?
- Are non-goals and fixed safety rules explicit?
- Are all owner choices and research blockers resolved or removed from scope?
- Are provider capabilities treated as runtime evidence rather than assumptions?
- Are architecture and trust boundaries enforceable by tests or static checks?
- Are failure, restart, retry, cancellation, partial success, and cleanup specified?
- Does every normative requirement map to acceptance and verification?
- Is the numeric test budget proportional to the risks?
- Are documentation, migration, backup, and rollback deliverables named?
- Are pending, action-required, partial, failed, and completed UX states concrete?

Readiness is necessary but not authorization to implement. The owner must still explicitly approve implementation.

## Current foundation set

| Capability | SDD | Why it exists before code |
| --- | --- | --- |
| Home Assistant App runtime | [App runtime and Ingress](home-assistant-app-runtime-and-ingress.md) | Packaging, lifecycle, authentication boundary, persistence, backup |
| Home Assistant-native UI | [UI foundation](home-assistant-native-ui.md) | Shared component families, host context, accessibility, responsive behavior, catalog, visual compatibility |
| Provider connections | [Provider connections and authorization](provider-connections-and-authorization.md) | OAuth/cookies, secrets, callback boundary, effective capabilities |
| Provider imports | [Library import and provider projections](library-import-and-provider-projections.md) | Completeness, provenance, unavailable items, retention |
| Recording identity | [Recording identity resolution](recording-identity-resolution.md) | Conservative matching, evidence, manual decisions |
| Playlist copy | [One-time playlist copy](one-time-playlist-copy.md) | Immutable plan, explicit omissions, safe external writes |
| Durable execution | [Durable operations and recovery](durable-operations-and-recovery.md) | Leases, checkpoints, retries, restarts, partial outcomes |

Persistent synchronization intentionally has no implementation SDD yet. It remains future scope until playlist ownership, conflict semantics, provider revision evidence, and the copy contract are resolved.

## Manual validation while the repository has no toolchain

Run after every SDD or catalog change:

```text
git diff --check
```

Also verify:

1. `catalog.json` parses as JSON and every referenced local path exists.
2. Each catalog capability has exactly one primary SDD.
3. Every SDD uses a catalog ID present in `catalog.json`.
4. Local Markdown links resolve.
5. Requirement IDs referenced by SDDs exist in the horizontal specifications.
6. `CATALOG.md` agrees with `catalog.json`.

A repository-native validator and generated catalog may be added after the implementation toolchain is selected; that tooling choice must not drive the application stack.
