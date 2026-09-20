# <Capability title>

- Status: Draft
- Date: YYYY-MM-DD
- Catalog capability ID: `<id from catalog.json>`
- Owners: Symphonia maintainers
- Scope: <one sentence>
- Related requirements: `<SYM-...>`
- Related decisions/research: <links>
- Required review gates: product UX, architecture, provider feasibility, testing, documentation, security/operations
- Open decisions blocking readiness: <none or explicit list>

> Start with [`README.md`](./README.md). Remove this note when the SDD is ready. Mark a non-applicable section explicitly and explain why.

## 1. Executive summary

Describe the user-visible outcome, recommended default, and principal safety/correctness rule.

```text
<entry point> -> <system transitions> -> <visible result>
```

## 2. Problem, current behavior, and evidence

### 2.1 Problem

Who is affected, what they cannot do safely, and why it matters.

### 2.2 Current behavior

State whether no implementation exists or describe verified behavior. Separate facts from assumptions.

### 2.3 Evidence and unknowns

- Repository specifications/ADRs:
- Official external sources:
- Community implementation evidence:
- Unknowns:

## 3. Actors, surfaces, and terminology

| Actor | Goal | Entry point | Visible surfaces |
| --- | --- | --- | --- |
| <actor> | <goal> | <event/action> | <App UI/HA/settings/docs/etc.> |

Define capability-specific terms and refer to the shared domain language.

## 4. Goals, non-goals, and fixed invariants

### 4.1 Goals

1. <Observable outcome>

### 4.2 Non-goals

1. <Explicitly excluded behavior>

### 4.3 Fixed invariants

1. <Rule configuration cannot weaken>

## 5. Product journey

| Stage | Proposed behavior | User/operator effect |
| --- | --- | --- |
| <stage> | <behavior> | <visible result> |

For three or more dependent transitions, include a flow/state diagram and a textual equivalent.

## 6. Functional behavior and state model

### 6.1 Happy path

1. <Observable step and owner>

### 6.2 Alternative and boundary paths

- <Alternative and consequence>

### 6.3 State machine

| State | Entered when | User-visible meaning | Allowed next states | Recovery/owner |
| --- | --- | --- | --- | --- |
| <state> | <fact> | <meaning> | <states> | <action> |

Specify duplicate, stale, out-of-order, cancellation, and partial behavior where applicable.

## 7. Configuration contract

| Input | Type | Recommended default | Allowed values/range | Scope/persistence |
| --- | --- | --- | --- | --- |
| `<name>` | <type> | <default and reason> | <bounded values> | <scope/snapshot> |

Define validation, precedence, migration, a meaningful alternative, and behavior intentionally not configurable.

## 8. Clean Architecture design

### 8.1 Responsibilities and dependency direction

| Boundary | Owns | Must not own/import |
| --- | --- | --- |
| Domain/pure policy | <decisions/invariants> | Provider/framework details |
| Application | <use cases/semantic ports> | Concrete SDK/process concerns |
| Adapters/data | <mapping and IO> | Product policy |
| Infrastructure/composition | <implementations/wiring> | Business decisions |
| Entrypoints/presentation | <input/view models> | Duplicated orchestration |

### 8.2 Contracts, durable state, and trust boundaries

- Pure decisions:
- Application contracts:
- Semantic ports:
- Durable state/schema ownership:
- Concurrency/idempotency:
- Trusted/untrusted inputs:
- Error mapping:

### 8.3 Executable architecture constraints

- <Dependency/cycle/schema/contract rule and planned automated check>

## 9. UI/UX and content contract

### 9.1 Information hierarchy

1. Current status.
2. Completed facts.
3. What happens next.
4. Required human action or an explicit statement that none is needed.
5. Impact and retained state.
6. Collapsed, sanitized technical evidence.

### 9.2 Representative states

Provide concrete content for pending, action required, partial, failed/blocked, and completed states. Use text, not color or icons alone.

### 9.3 Accessibility and localization

- Locale source/fallback:
- Keyboard/focus/announcement behavior:
- Narrow/mobile behavior:
- Text alternative for diagrams:
- Sanitization of provider/user content:

## 10. Failure, recovery, and cleanup

| Failure/partial state | User impact | Retained facts | Automatic retry | Required action | Cleanup |
| --- | --- | --- | --- | --- | --- |
| <condition> | <impact> | <facts> | <bounded policy> | <action> | <rule> |

Errors follow `impact -> cause -> next action -> retained state`.

## 11. Security, permissions, and privacy

1. <Least privilege and authorization>
2. <Untrusted input and boundary validation>
3. <Secret/PII/storage/logging rule>
4. <Replay/forgery/abuse protection>

## 12. Observability and operational UX

- User-facing state:
- Logs, metrics, and correlation:
- Pending external dependency versus service failure:
- Rate-limit/retry visibility:
- Notification/noise budget:

## 13. Compatibility, migration, rollout, and rollback

- Existing data/in-flight operations:
- Schema/configuration migration:
- Rollout stages:
- Rollback and irreversible effects:

## 14. Testing strategy and numeric budget

| Area | Minimum distinct cases | Behaviors/risks covered |
| --- | ---: | --- |
| Domain/configuration/planning | <n> | <list> |
| State/application/idempotency/races | <n> | <list> |
| Adapters/contracts | <n> | <list> |
| HTTP/UI/accessibility/sanitization | <n> | <list> |
| Integration/security/migration | <n> | <list> |
| **Total** | **<n>** | No double counting |

Define deterministic fakes/clocks/IDs, coverage expectations, contract fixtures, live-smoke isolation, and required human evidence.

## 15. Documentation and discoverability

| Audience | Artifact | Required content | Validation/navigation |
| --- | --- | --- | --- |
| User | <page> | <journey/default/examples> | <link/fixture check> |
| Setup owner | <page> | <permissions/configuration> | <contract check> |
| Operator | <page> | <states/recovery/cleanup> | <decision tree> |
| Contributor | <page> | <architecture/contracts> | <architecture check> |

## 16. Acceptance scenarios

1. Given `<state>`, when `<event>`, then `<observable result>`.
2. <Alternative/boundary/invalid case>.
3. <Duplicate/out-of-order/cancellation/recovery case>.
4. <Failure before irreversible effect>.
5. <Partial success after irreversible effect>.
6. <Security/permission/forged-input case>.
7. <UI/accessibility/localization case>.
8. <Documentation/configuration/architecture-contract case>.

## 17. Requirements traceability

| Requirement | Policy/use case/adapter/presentation | Test or evidence | Documentation |
| --- | --- | --- | --- |
| `<SYM-...>` | <owner> | <verification> | <page> |

## 18. Implementation sequence

1. Resolve blockers and approve contracts/configuration.
2. Add failing architecture/contract tests and pure policies.
3. Add application state/use cases and deterministic tests.
4. Add adapters and contract tests.
5. Add presentation, accessibility, and documentation.
6. Add migration/recovery/security evidence and integration validation.

## 19. Definition of Done

- [ ] Status is `Ready for implementation` and explicit owner approval to implement exists.
- [ ] Every normative requirement has acceptance and traceability.
- [ ] Architecture boundaries and external contracts are automatically enforced.
- [ ] Numeric test budget and stated coverage pass.
- [ ] Configuration, migration, backup, rollback, and recovery agree.
- [ ] Pending, action-required, partial, failed, and completed UX states are verified.
- [ ] Accessibility, localization, sanitization, and secret-safety gates pass.
- [ ] User/setup/operator/contributor documentation is complete and discoverable.
- [ ] Catalog status and implementation evidence are current.
- [ ] No readiness-blocking decision remains.

## 20. References and decisions

- Primary sources:
- Related SDDs/ADRs:
- Accepted and rejected alternatives:
- Follow-up work outside scope:
