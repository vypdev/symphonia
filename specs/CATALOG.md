# Capability and SDD catalog

**Catalog version:** 1

This is the human-readable view of [`catalog.json`](./catalog.json). Until generation tooling exists, both files are updated together and checked during review.

| Capability ID | Status | Primary SDD | Readiness summary |
| --- | --- | --- | --- |
| `home-assistant-app-runtime` | Draft | [Home Assistant App runtime and Ingress](home-assistant-app-runtime-and-ingress.md) | Blocked by storage/recovery, supported platform matrix, and secret-key design |
| `home-assistant-native-ui` | Ready for review | [Home Assistant-native UI foundation](home-assistant-native-ui.md) | Product direction is accepted; blocked from implementation readiness by the supported matrix, frontend/build choice, public host-context validation, and visual-reference procedure |
| `provider-connections-and-authorization` | Draft | [Provider connections and authorization](provider-connections-and-authorization.md) | Blocked by OAuth boundary and provider feasibility spikes |
| `library-import-and-provider-projections` | Draft | [Library import and provider projections](library-import-and-provider-projections.md) | Blocked by provider completeness, retention, and representative scale |
| `recording-identity-resolution` | Draft | [Recording identity resolution](recording-identity-resolution.md) | Blocked by the labeled corpus and accepted automatic-link policy |
| `one-time-playlist-copy` | Draft | [One-time playlist copy](one-time-playlist-copy.md) | Blocked by unresolved-entry policy and proven target write semantics |
| `durable-operations-and-recovery` | Draft | [Durable operations and recovery](durable-operations-and-recovery.md) | Blocked by the persistence/lease/restart spike and operating targets |

## Foundation evidence boundary

`home-assistant-app-runtime` and `durable-operations-and-recovery` have owner-approved foundation evidence in `catalog.json`. The listed code, tests, and documentation cover only dependency-free persistence, lifecycle composition, packaging, redaction, diagnostics, backup preflight, and deterministic worker mechanics. They do not change either capability's `Draft` status or clear its blockers; OAuth, secret ownership, complete migration/restore, production topology, UI, and provider-vertical acceptance remain gated by their SDDs.

## Deliberately absent

There is no implementation SDD for persistent playlist synchronization. It remains specified only at the domain/future level until:

- the one-time copy contract is accepted and proven;
- provider-owned versus Symphonia-owned playlist state is decided;
- change attribution and conflict policy are accepted; and
- provider revision/removal/reorder capabilities are demonstrated.

Apple Music also remains future provider research rather than a catalog capability. Promoting it requires its feasibility gates and an explicit product-scope decision.
