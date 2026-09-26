# ADR 0002: Copy and synchronization are distinct concepts

- **Status:** accepted
- **Date:** 2026-09-20

## Context

A user may want either a one-time transfer or a continuing relationship. Treating every copy as synchronization creates hidden future behavior; treating sync as repeated stateless copy loses baselines, attribution, direction, and conflict policy.

The MVP should be useful before complex persistent synchronization is settled.

## Decision

Model a playlist copy as a finite `CopyPlan` and `CopyRun` derived from a captured source snapshot. Completion creates no continuing behavior.

Model future synchronization as a separate durable `SyncRelationship` with participants, direction/mode, baseline, trigger/schedule, and conflict/unmatched policies. Each sync execution is an auditable run of that relationship.

The MVP implements copy. Sync follows after copy semantics and provider feasibility are validated.

## Alternatives considered

### Every copy creates a sync relationship

Rejected because users could trigger unexpected later writes and the MVP would need conflict/schedule semantics immediately.

### Sync is a scheduled copy with no durable relationship

Rejected because the system could not reliably attribute changes, detect concurrent edits, or explain deletion/reordering conflicts.

### Implement sync before copy

Rejected because it increases provider-write and recovery risk before matching and copy plans are proven.

## Consequences

Positive:

- one-time intent is explicit and bounded;
- copy can deliver value with a smaller, safer workflow;
- future sync has a correct home for baselines and policy;
- operation history can distinguish a retry from a new recurring run.

Trade-offs:

- copy history must retain enough source/target evidence to inform future sync design;
- users who want ongoing mirroring must wait for a later release;
- promoting a copied pair into sync requires an explicit future workflow.
