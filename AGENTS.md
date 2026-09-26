## Product specifications and SDDs

When creating, revising, reviewing, or implementing product behavior:

1. Read [`specs/README.md`](specs/README.md) and the applicable SDD in full.
2. Consult [`specs/catalog.json`](specs/catalog.json) for capability status, blockers, and evidence.
3. Start new SDDs from [`specs/_template.md`](specs/_template.md). Adapt sections proportionally, but mark non-applicable concerns explicitly instead of deleting them silently.
4. Keep global product/domain/architecture requirements in `docs/`; SDDs assemble those requirements into one vertical, implementation-driving capability contract. Resolve conflicts rather than choosing one document silently.
5. Do not implement a capability whose SDD is not `Ready for implementation`, and do not begin production implementation without explicit owner approval even when the SDD is ready.
6. Update the SDD, catalog evidence, tests, user/operator documentation, and relevant ADRs together when an observable or architectural contract changes.
7. Include concrete user flows, states, failure/recovery behavior, security boundaries, a numeric test budget, acceptance scenarios, and requirement traceability.
8. Treat provider documentation and community implementations as dated evidence, not permanent guarantees. Keep official API research separate from community implementation evidence.

Until a repository-native specification validator is selected, every SDD change must at minimum pass the manual checks listed in `specs/README.md`.
