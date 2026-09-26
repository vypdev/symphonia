# Domain model

**Status:** provider-independent core accepted; playlist ownership and matching policy proposed/open
**Last reviewed:** 2026-09-20

## Model boundary

Symphonia models a person's relationship with recordings and provider collections. It does not model audio files or playback. Provider payloads enter through adapters and are translated into this language before use by product workflows.

This document specifies concepts and invariants, not database tables or API schemas.

## Ubiquitous language

| Term | Meaning | Important distinction |
| --- | --- | --- |
| **Musical work** | An abstract composition: melody, lyrics, and authorship independent of a performance. | “Hallelujah” as a composition is not Leonard Cohen's recording or a cover. Not an MVP identity target. |
| **Recording** | A particular recorded performance, mix, edit, or version. This is the primary provider-independent identity in the MVP. | Studio, live, acoustic, cover, remix, remaster, clean, and explicit versions may be different recordings. |
| **Symphonia track** | User-facing shorthand for a `Recording`; not a separate provider-shaped object. | Avoid using unqualified “track” in designs where identity matters. |
| **Release** | A published album, single, EP, or compilation edition containing recordings. | Different releases can contain the same recording; release identity is not recording identity. |
| **Artist credit** | The ordered credited performers attached to a recording or release. | A credit is not yet a canonical person/group identity. |
| **Provider** | A type of external system, such as Spotify or YouTube. | A provider is not an account. |
| **Provider connection** | One authorized external account plus its effective capabilities and credential reference. | More than one connection may eventually exist for one provider. |
| **Provider track** | A provider catalog item that represents or makes a recording available. | It retains the provider ID and may have incomplete or conflicting metadata. A YouTube video is a provider track only when used as a music candidate. |
| **Provider playlist** | An ordered collection owned by a provider/account and imported into Symphonia. | It is not automatically a Symphonia-owned logical playlist. |
| **Playlist entry** | One occurrence at one position in a playlist snapshot. | Repeated tracks are separate entries and must not be collapsed. |
| **Snapshot** | Symphonia's immutable observation of provider state at a point/version. | It does not claim the provider is still unchanged. |
| **Identity link** | The assertion that one provider track represents one recording. | The assertion has origin, evidence, confidence class, and lifecycle. |
| **Candidate** | A possible identity link awaiting automatic or manual disposition. | Candidate does not mean match. |
| **Manual resolution** | A user's accepted or rejected identity assertion. | It outranks later automatic guesses until explicitly invalidated or revoked. |
| **Copy plan** | Immutable, non-mutating instructions derived from one source snapshot and target capabilities. | It is not a sync relationship. |
| **Copy run** | One finite execution of an accepted copy plan. | A retry continues the logical run when safe; a re-plan is a new run. |
| **Sync relationship** | Persistent policy connecting two or more playlist projections. | It has recurring runs, baselines, direction, and conflict semantics. Post-MVP. |
| **Operation** | User-visible unit of work with status, checkpoints, outcomes, and issues. | An operation may contain many provider requests. |
| **Issue** | An actionable mismatch, ambiguity, provider failure, or policy conflict attached to an operation/item. | Exceptions and logs alone are not the product history. |

## Conceptual relationships

```text
LocalUser
  └─ ProviderConnection ── Provider
       ├─ imports ── ProviderTrack ── IdentityLink ── Recording
       └─ imports ── ProviderPlaylist
                       └─ ordered PlaylistEntry ── ProviderTrack

ProviderPlaylistSnapshot ── source of ── CopyPlan
CopyPlan ── executed as ── CopyRun ── emits ── OperationIssue

Future: PlaylistProjection(s) ── governed by ── SyncRelationship
```

The arrows do not imply persistence ownership. In particular, deleting a connection does not make a recording cease to exist.

## Core entities and value objects

### Recording

The canonical matchable item for the MVP.

Minimum conceptual attributes:

- stable Symphonia identifier;
- display title and version descriptors;
- ordered artist credits;
- duration and explicitness when known;
- recording identifiers such as ISRC, each with provenance;
- descriptive release metadata when useful to matching;
- creation/update timestamps; and
- merged/superseded lifecycle state if deduplication is later required.

A Recording's descriptive fields can be synthesized from provider evidence, but every value SHOULD retain provenance or derivation. Provider metadata disagreement must not be erased by last-write-wins updates.

### Musical work

Musical work is included in the language to prevent a category error, not as an MVP aggregate. The MVP MUST NOT merge covers merely because their titles and writers coincide. A later model may connect many recordings to one work.

### Provider connection

Minimum conceptual attributes:

- stable Symphonia identifier;
- provider type and immutable provider-account identity;
- user-chosen display name;
- credential reference, never a token embedded in normal domain payloads;
- requested, granted, and effective capability sets;
- connection health and user-action state;
- token/authorization expiry metadata when available;
- last attempted/successful import times; and
- policy/terms acknowledgement metadata where required.

### Provider track

Minimum conceptual attributes:

- provider type, connection where access is account/market dependent, and provider object ID;
- provider URI/URL when safe to retain;
- provider media kind and availability;
- original metadata snapshot and normalized matching fields;
- provider revision/ETag/update markers when available;
- observed and refresh-by timestamps; and
- policy classification for retention and deletion.

The external identity key is at least `(provider type, provider object type, provider object ID)` and includes a provider-instance/connection, market, or catalog namespace whenever the provider does not guarantee global uniqueness. It MUST NOT use a mutable title. Whether the same proven-global catalog ID shared through two connections is stored once or projected per connection is a persistence design question; account-specific availability must remain representable. A personal or dynamic collection ID MUST NOT be assumed globally unique merely because it is stable inside one account.

### Provider playlist and snapshot

A provider playlist retains its external identity, owner, visibility, description, collaborative flags, provider revision token, and capability constraints. Import creates an immutable snapshot with ordered entries.

Each entry records:

- stable snapshot-local entry ID;
- ordinal/position;
- provider item ID and media kind;
- occurrence-specific provider entry ID when exposed;
- added-at/added-by metadata when exposed;
- availability at observation time; and
- eventual recording resolution state.

An entry can be unavailable or deleted while its historical place in a snapshot remains meaningful.

### Identity link and candidate

An accepted identity link contains:

- provider track ID and recording ID;
- origin: deterministic external ID, heuristic, or manual;
- confidence class;
- positive and negative evidence;
- resolver name and version;
- actor and timestamps;
- status: active, revoked, superseded, or invalidated; and
- invalidation reason where applicable.

A rejected candidate pair is durable evidence and MUST be consulted by future resolver versions. It is not represented as the absence of a link.

### Operation, step, and issue

An operation is the user-facing aggregate for import, resolution, copy, and later sync. It owns:

- type, initiator, correlation ID, and idempotency key;
- input references and immutable plan/version where applicable;
- state and timestamps;
- resumable steps/checkpoints;
- item outcomes;
- sanitized provider-request metadata;
- issues and their resolution state; and
- result summary.

Operational events may be pruned under a retention policy, but the final audit summary and manual decisions have separate retention lifecycles.

## Domain invariants

1. A provider track has zero or one active identity link to a recording.
2. A recording may have many provider tracks, including multiple tracks from the same provider.
3. A provider ID is never a Symphonia recording ID.
4. An ISRC is evidence for recording identity, not proof of musical-work identity or infallible uniqueness.
5. An imported playlist's order and duplicate occurrences are significant.
6. Provider facts, derived values, and user decisions have separate provenance.
7. A manual decision is never overwritten silently by an automatic resolver.
8. A plan is immutable; changed inputs produce a new plan version.
9. A capability is evaluated for the adapter, connection, affected object, and current provider health at operation time, not assumed globally from provider type.
10. Historical provider writes are append-only audit facts, even when a later compensating action reverses their effect.

## Identity resolution specification

### The problem

Providers describe overlapping but non-identical catalogs. Metadata can be missing, localized, inconsistent, wrongly attributed, market-specific, or duplicated. The resolver must decide whether two representations refer to the same recording without collapsing a musical work's different performances or versions.

ISRC is valuable because it identifies recordings, but it is not sufficient alone: provider data may omit it, reuse it unexpectedly, attach it at a different version granularity, or expose a video rather than a label-issued recording. Title similarity is weaker and can confuse covers, live performances, edits, and remasters.

### Resolution pipeline

The following stages are requirements; their algorithms and thresholds remain open:

1. **Normalize without destroying source data.** Produce comparison fields for Unicode, punctuation, featured artists, version tokens, and durations while retaining originals.
2. **Generate candidates.** Use exact identifiers where available and provider search/metadata for bounded candidate retrieval.
3. **Evaluate evidence.** Consider identifiers, title, ordered/credited artists, duration tolerance, release context, explicitness, version markers, market availability, and provider type.
4. **Classify.** Produce `exact`, `high_confidence`, `ambiguous`, or `unmatched` as a candidate assessment, then set the provider track's resolution state.
5. **Explain.** Store the material evidence and resolver version.
6. **Apply policy.** Only policy-approved classes may create automatic links; ambiguous results enter the review queue.
7. **Learn decisions.** Persist accepted and rejected pairs for deterministic reuse. “Learn” means rule reuse, not training an ML model on provider content.

### Confidence semantics

| Class | Meaning | Permitted MVP behavior |
| --- | --- | --- |
| `exact` | Meets a future, explicit deterministic rule with no known contradictory evidence. | May auto-link once exact rules are approved. |
| `high_confidence` | Strong multi-field evidence but not deterministic. | Auto-link versus review is an open product threshold. |
| `ambiguous` | At least two plausible candidates or material contradictory evidence. | MUST require user resolution before a strict copy. |
| `unmatched` | No acceptable candidate was found within bounded search. | MUST remain visible; MAY be retried after metadata/provider changes. |

The labels are not percentages. No numeric thresholds are accepted in this baseline.

### Manual-resolution behavior

- Accepting a candidate activates or creates an identity link.
- Rejecting a candidate stores a negative assertion scoped to the two identities.
- “Distinct recording” creates a new Recording rather than linking to an inappropriate existing one.
- “Defer” records that the user intentionally postponed the choice and avoids presenting it as a new failure on every screen.
- Revocation preserves who made the original decision and why it changed.
- A provider object that changes identity-like metadata materially is flagged for review; it is not silently rematched over a manual link.

## Playlist copy model

Copy is a finite workflow:

```text
source snapshot → resolution/capability analysis → immutable plan
                → user acceptance → target writes → reconciliation → result
```

### Plan content

A copy plan records source playlist/snapshot, target connection, intended target name/visibility, source entry order, target provider track for each ready entry, match evidence, non-ready reason, capabilities observed, unresolved-item policy, and a digest used to detect tampering or accidental version mixing.

Planning MUST NOT mutate a provider. Target search calls used during planning are reads.

### Execution behavior

Execution creates or selects a target only as described in the accepted plan. Writes are checkpointed in provider-safe batches. On retry, Symphonia first determines whether a timed-out write took effect. If provider APIs cannot make a write provably idempotent, the result becomes `needs_reconciliation` rather than risking duplicate entries.

The following remain open for the copy RFC:

- strict all-resolved versus best-effort as the default;
- whether an existing target can be appended to in the MVP;
- rollback/cleanup behavior after partial target creation;
- visibility/name collision behavior; and
- user confirmation rules for a re-executed plan.

## Playlist synchronization model

Persistent sync is post-MVP but constrains what history copy must retain.

- **SYM-SYNC-001:** A sync relationship MUST be a durable object separate from its individual runs.
- **SYM-SYNC-002:** A relationship MUST declare participants, direction/mode, field and entry policies, schedule/trigger, unmatched-item policy, and conflict policy.
- **SYM-SYNC-003:** Each run MUST compare current provider snapshots with a known baseline; current-state comparison alone is insufficient to attribute changes.
- **SYM-SYNC-004:** Symphonia MUST distinguish observed external changes, writes made by Symphonia, and uncertain changes.
- **SYM-SYNC-005:** Add, remove, reorder, metadata change, duplicate-entry change, and playlist deletion MUST be distinct change kinds where provider evidence permits.
- **SYM-SYNC-006:** A run MUST be replay-safe and MUST checkpoint provider writes.
- **SYM-SYNC-007:** Conflicts MUST remain visible until a declared policy or user action resolves them.
- **SYM-SYNC-008:** A provider without sufficient change/version evidence MUST declare degraded sync semantics; polling MUST NOT be presented as lossless real-time sync.

Potential modes are:

- **source-of-truth/mirror:** one projection defines desired state; target divergence is overwritten or reported according to policy;
- **add-only:** newly observed additions propagate; removals and reorderings do not;
- **bidirectional:** changes on both sides propagate using a common baseline and explicit conflict rules.

These modes are vocabulary, not accepted MVP behavior.

## Playlist ownership RFC: provider-owned or Symphonia-owned

This decision is intentionally open and must be made before persistent sync is designed.

### Option A — provider-owned playlists with relationships

Provider playlists remain primary objects. A copy points from one provider snapshot to target writes; a sync relationship connects provider playlists.

**Advantages**

- Matches the initial user mental model: “copy Spotify/Rock to YouTube/Rock.”
- Requires less local authoring UI and fewer rules about which edits are authoritative.
- Supports a smaller copy-first MVP and respects provider ownership/visibility semantics.

**Costs**

- Bidirectional sync needs careful baselines and conflict attribution.
- Losing/deleting a provider playlist can remove an apparent anchor.
- Relationships with more than two projections and offline editing are awkward.
- A later logical-playlist model may require migration.

### Option B — Symphonia-owned logical playlists with projections

A logical playlist is authoritative inside Symphonia; provider playlists are projections of its desired state.

**Advantages**

- Gives the user a durable provider-independent object.
- Makes multiple projections and source replacement conceptually clean.
- Provides a natural place for local edits, desired order, and policy.

**Costs**

- Requires rules for importing ownership, provider-side edits, projection drift, deletion, and conflicts immediately.
- Risks turning Symphonia into another library editor before basic interoperability works.
- Provider limitations can make a projection unable to represent the logical list exactly.

### Option C — staged hybrid

Ship provider-owned copy first, retain immutable snapshots and stable recording identities, then allow a user to promote a relationship or imported playlist into a logical playlist after a dedicated RFC.

This is the current **proposed direction**, not an accepted decision. It minimizes MVP scope while preserving a migration path. Implementation must avoid naming a provider playlist ID as a logical playlist ID and must retain origin/projection metadata.

## Lifecycle and deletion

Provider-sourced metadata is a renewable observation and may be subject to provider-specific refresh/deletion policy. User-authored resolution decisions and operation facts are locally owned, but they must not retain prohibited provider payloads indefinitely by embedding raw metadata.

Deletion design MUST distinguish:

- disconnect and revoke credentials;
- delete cached provider data under policy;
- delete a provider object through an authorized operation;
- delete local history; and
- forget/export all local user data.

Exact retention periods and cascade behavior require the security/privacy RFC.

## Deliberately unresolved domain questions

- Can one ProviderTrack map to different Recordings by market or provider metadata revision?
- When are two ISRC-bearing items automatically exact, and what contradictory evidence blocks that?
- Are clean and explicit variants always distinct Recordings for the user's purpose?
- Should releases and artists become canonical entities in the MVP or remain credited metadata?
- What is the stable identity of a YouTube music candidate: video, song entity, or another officially exposed object?
- What library membership means across providers: saved track, liked video/song, followed release, or a provider-specific collection?
- Which playlist ownership option should govern post-copy synchronization?
