## Product specifications and SDDs

When creating, revising, reviewing, or implementing product behavior:

1. Read [`specs/README.md`](specs/README.md) and the applicable SDD in full.
2. Consult [`specs/catalog.json`](specs/catalog.json) for capability inventory and evidence; read design readiness and blockers in the owning SDD.
3. Start new SDDs from [`specs/_template.md`](specs/_template.md). Adapt sections proportionally, but mark non-applicable concerns explicitly instead of deleting them silently.
4. Keep global product/domain/architecture requirements in `docs/`; SDDs assemble those requirements into one vertical, implementation-driving capability contract. Resolve conflicts rather than choosing one document silently.
5. Do not implement a capability whose SDD is not `Ready for implementation`, and do not begin production implementation without explicit owner approval even when the SDD is ready.
6. Update the SDD, catalog evidence, tests, user/operator documentation, and relevant ADRs together when an observable or architectural contract changes.
7. Include concrete user flows, states, failure/recovery behavior, security boundaries, a numeric test budget, acceptance scenarios, and requirement traceability.
8. Treat provider documentation and community implementations as dated evidence, not permanent guarantees. Keep official API research separate from community implementation evidence.

Follow Copilot's SDD system strictly from the outset: its standard, template,
SDK v1 catalog fields/statuses, generated index, validation, and Action-owned
publication flow. Do not invent a parallel schema, readiness catalog, adapter,
or publication mechanism. Request improvements or complements in a new issue in
[`vypdev/copilot`](https://github.com/vypdev/copilot/issues/new/choose); until
accepted upstream, continue following the supported system.

Run `npm run validate:specifications` (equivalently
`pnpm run validate:specifications`) and regenerate catalog metadata with
`npm run generate:specifications`. Copilot's validation policy is vendored
unchanged; a provenance-tracked renderer bugfix preserves nested links. Read
[`the adoption notes`](docs/development/copilot-sdd-adoption.md)
for provenance, evidence limits, and the manual readiness review. Passing a
structural check does not approve implementation or establish live acceptance.

<!-- copilot:agent-guidance:start -->
Before repository work, use the `copilot-repository-workflow` skill and read `.copilot/AGENT_GUIDE.md`. Managed remote branches are owned by the GitHub Action.
<!-- copilot:agent-guidance:end -->
