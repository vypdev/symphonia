# Provider specification

**Status:** proposed contract; specific support is a dated research fact
**Last reviewed:** 2026-09-20

## Purpose

Provider adapters translate external authentication, catalog, library, and playlist behavior into Symphonia concepts. The core asks for semantic capabilities and operations; it never branches on `spotify` or `youtube` to decide domain policy.

This document states what Symphonia needs. [Provider research](provider-research.md) separately records what current official APIs appear to support, while the [Home Assistant music ecosystem review](home-assistant-ecosystem-review.md) records reusable implementation patterns and cautions from existing projects.

## Provider, connection, and adapter

- A **Provider** is a named adapter kind and version with a manifest describing its provenance, maturity, configuration, dependencies, and declared capability ceiling.
- A **Provider connection** is one authorized external account with granted scopes, market/account constraints, health, and effective capabilities.
- An **Adapter** implements provider ports for a provider kind. It converts provider DTOs/errors into normalized types and keeps provider-specific payloads outside the core.

Capabilities belong to a connection at a point in time. They may depend on account tier, scopes, market, API mode, app registration, quota, policy approval, object ownership, or playlist type.

An effective workflow capability is the intersection of:

1. the adapter's statically declared capability ceiling;
2. the connection's current account, scopes, configuration, and health;
3. the target object's ownership/type/editability constraints; and
4. live provider availability or policy state.

### Adapter provenance and support classification

The manifest keeps independent axes instead of collapsing risk into one “supported” boolean:

- **access basis:** `official_public_api`, `official_sdk_or_contract`, or `unofficial_reverse_engineered`;
- **maturity:** `experimental`, `beta`, or `stable`;
- **product support:** `disabled`, `best_effort`, or `supported`;
- upstream project/library names and pinned version constraints;
- last API/terms/security review date; and
- whether multiple configured instances are supported.

The UI may render a concise combined label, but it MUST retain these underlying facts. A mature adapter can still rely on an unofficial access basis, while an official API adapter can remain experimental.

## Capability descriptor

A boolean is too weak. Each capability descriptor contains:

- stable capability ID and schema version;
- support state: `supported`, `unsupported`, `degraded`, `unknown`, or `temporarily_unavailable`;
- evidence source and last-probed time;
- required scopes/authorization and missing grants;
- ownership/media/visibility restrictions;
- batch size, pagination, ordering, duplicate, and atomicity behavior;
- quota cost/rate-limit dimensions when known;
- revision/concurrency token behavior;
- retention or policy constraints; and
- user-facing reason and remediation.

`unknown` MUST NOT be treated as supported. `degraded` means the operation is possible but cannot meet at least one normal semantic guarantee; the descriptor explains which.

## Capability catalog

The initial catalog is intentionally granular:

### Account and authorization

- `account.authorize.offline`
- `account.profile.read`
- `account.grant.refresh`
- `account.grant.revoke`

### Library

- `library.saved_tracks.read`
- `library.saved_tracks.add`
- `library.saved_tracks.remove`
- `library.albums.read`
- `library.changes.incremental`

### Playlists

- `playlist.list.owned`
- `playlist.list.followed`
- `playlist.read.metadata`
- `playlist.read.entries`
- `playlist.revision.read`
- `playlist.create`
- `playlist.update.metadata`
- `playlist.delete`
- `playlist.entries.add`
- `playlist.entries.remove`
- `playlist.entries.reorder`
- `playlist.entries.replace`
- `playlist.duplicates.preserve`
- `playlist.changes.push`

### Catalog and metadata

- `catalog.track.get`
- `catalog.track.search`
- `catalog.track.search_by_isrc`
- `metadata.isrc.read`
- `metadata.duration.read`
- `metadata.release.read`
- `metadata.artist_credits.read`
- `metadata.version_markers.read`

Adapters MAY add namespaced experimental capabilities, but product workflows use only cataloged stable capabilities until the catalog is revised.

## Capability requirements by workflow

| Workflow | Required capabilities | Optional enrichment |
| --- | --- | --- |
| Import playlists | list owned or followed, metadata read, entries read | revision read, incremental changes |
| Import saved library | saved tracks read | albums read, incremental changes |
| Match source item | track get plus useful metadata | ISRC, release, search |
| Copy to new playlist | target search/get, playlist create, entries add | metadata update, duplicates preserve, revision read |
| Strict mirror sync | read/revision on both, target add/remove/reorder or replace | push changes, conditional writes |
| Add-only sync | read/revision on source, target search/get/add | push changes |

A workflow MUST fail during planning with a typed capability explanation if a required capability is absent. It must not discover this after creating a partial target where a preflight probe was possible.

## Normalized provider ports

Exact language signatures are deferred, but an adapter must cover these behaviors:

### Connection lifecycle

- describe configuration and authorization requirements;
- begin authorization and validate a one-time callback;
- identify the external account without using mutable display names;
- refresh or reauthorize grants;
- probe effective capabilities; and
- revoke/disconnect and describe cleanup obligations.

### Read/import

- page through saved/library items and playlists with bounded page sizes;
- fetch playlist metadata, revision evidence, and ordered entries;
- fetch provider track metadata in batches where supported;
- represent deleted, unavailable, private, local-file, episode/non-music, and unknown media explicitly; and
- produce provider cursors/ETags only as opaque adapter-owned values.

### Search/mapping

- search for bounded track candidates using supported provider fields;
- fetch enough metadata to explain a candidate;
- return stable external IDs and availability for the authorized account/market; and
- report when search is generic video/content search rather than a music catalog search.

### Write

- create a playlist with explicit visibility and description semantics;
- add ordered entries using declared batch sizes;
- where supported, remove, reorder, replace, rename, or delete;
- return revision identifiers and per-item/batch outcomes; and
- provide a reconciliation read for unknown write outcomes.

## Adapter requirements

- **SYM-PROV-001:** Domain and application code MUST depend on provider ports and normalized types, never provider SDK types.
- **SYM-PROV-002:** An adapter MUST report effective connection capabilities before a workflow plan is accepted.
- **SYM-PROV-003:** Capability detection MUST combine static documented support, granted scopes, account/object restrictions, configuration, and safe runtime probes where needed.
- **SYM-PROV-004:** An adapter MUST implement pagination without silently truncating results and MUST expose completeness/freshness.
- **SYM-PROV-005:** An adapter MUST preserve provider IDs as opaque strings and MUST NOT infer identity from URL shape.
- **SYM-PROV-006:** Unknown media types and unavailable items MUST survive import as explicit normalized states.
- **SYM-PROV-007:** Adapter calls MUST have bounded connect/read/overall timeouts and cooperative cancellation.
- **SYM-PROV-008:** Provider errors MUST map to the normalized error taxonomy while preserving a sanitized provider code and correlation ID.
- **SYM-PROV-009:** Adapter logging MUST NOT include tokens, authorization codes, client secrets, raw authentication headers, or unrestricted payloads.
- **SYM-PROV-010:** Provider write methods MUST declare idempotency/reconciliation semantics; “retryable” is not a sufficient declaration.
- **SYM-PROV-011:** Rate-limit handling MUST honor provider reset or `Retry-After` signals and share budget state across concurrent work for the connection/provider.
- **SYM-PROV-012:** Adapter contract tests MUST run against deterministic fixtures/fakes without network access.
- **SYM-PROV-013:** Live-provider smoke tests MUST be separately enabled, use dedicated accounts/data, clean up safely, and never gate ordinary contributor tests.
- **SYM-PROV-014:** Raw provider payload storage MUST be minimized, versioned, and governed by provider retention/deletion policy.
- **SYM-PROV-015:** An adapter MUST publish its terms/API research review date and fail visibly when a known incompatible provider contract version is detected.
- **SYM-PROV-016:** Reverse-engineered or unofficial access MUST be a distinct adapter with explicit user opt-in and risk labeling; it MUST NOT masquerade as an official capability.
- **SYM-PROV-017:** Every adapter manifest MUST publish access basis, maturity, product-support level, upstream dependencies, multi-instance support, and last review date.
- **SYM-PROV-018:** An external object identity MUST include its object type and MUST include a provider-instance or connection namespace whenever upstream IDs are not proven globally unique.
- **SYM-PROV-019:** Planning MUST calculate effective capabilities from adapter, connection, object, and live-health constraints; a connection-wide capability MUST NOT override an object-level denial such as a read-only playlist.
- **SYM-PROV-020:** Unofficial or `best_effort` status MUST be visible before authorization and again in any plan that depends on that adapter.

## Normalized error taxonomy

Adapters return a stable category plus safe detail:

```text
authentication_required
authorization_revoked
permission_denied
capability_unavailable
not_found
item_unavailable
invalid_request
rate_limited
provider_unavailable
timeout
network_error
conflict
unknown_write_outcome
provider_contract_changed
```

The normalized error includes retry advice, retry-after instant when known, whether user action is required, provider code, and safe operation context. It never includes raw response bodies by default.

## Import and freshness contract

An import session records:

- connection and adapter version;
- requested collections/capabilities;
- start/end time and completeness;
- pages/items observed, skipped, invalid, or inaccessible;
- provider cursors/revisions as opaque values;
- per-object observed-at and refresh-by metadata;
- quota consumed when observable; and
- terminal/warning issues.

Only a complete import may mark objects missing from the complete provider result as no longer observed. A failed or truncated import MUST NOT mass-delete prior state.

## Provider-specific configuration

The adapter may define typed, validated configuration fields such as client ID, redirect registration hints, market, or conservative request budget. The general App options file is not a secret store. Configuration descriptions MUST identify which values are secret and where they are persisted.

Provider-specific configuration does not leak into recording, playlist, or operation aggregates. Use adapter-owned configuration referenced by the connection.

## Adding a provider

A new provider proposal must include:

1. official versus unofficial status and applicable terms;
2. a dated capability matrix using this catalog;
3. authentication, token lifecycle, callback, and self-hosting analysis;
4. data-retention/deletion obligations;
5. rate/quota behavior and write idempotency analysis;
6. mapping of provider media types to domain types;
7. fixture-based contract tests and an optional live-smoke plan; and
8. UI limitations and user-facing risk language.

Adding a provider must not require a new field on `Recording` solely because the provider returns it; provider-specific metadata belongs to the representation unless promoted through a provider-independent domain decision.
