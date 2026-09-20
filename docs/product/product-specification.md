# Product specification

**Status:** proposed baseline for owner review
**Last reviewed:** 2026-09-20

## Vision

Symphonia is a self-hosted personal music hub through which a person can see and manage their music across providers. Symphonia owns the user's provider-independent view of music; Spotify, YouTube, Apple Music, Plex, Navidrome, and future services are replaceable representations and execution targets.

The product initially optimizes for trustworthy library interoperability: import, explain, match, review, and copy. It is not primarily a playback surface.

## Product principles

1. **The user's model comes first.** Provider objects never become the canonical domain merely because they are convenient.
2. **Uncertainty is visible.** An ambiguous match is a user decision, not a hidden guess.
3. **Writes are previewable and explainable.** A user can see what will happen before a provider is mutated and what happened afterward.
4. **Provider differences remain explicit.** The UI and workflows degrade according to declared capabilities rather than pretending that all providers are equivalent.
5. **Self-hosted is a product constraint.** Operation, backup, upgrades, credentials, and recovery must be understandable to a homelab operator.
6. **Home Assistant is the primary host, not the domain boundary.** The primary package is a Home Assistant App with an Ingress UI, while the same core remains independently runnable and testable.

## Users

The MVP supports one local Symphonia user. That user operates the installation and owns the provider connections; in Home Assistant App mode the management surface is initially limited to authenticated administrators. The data model MUST NOT make a provider type synonymous with a single global account; future versions may allow several connections to the same provider.

Multi-user authorization, sharing between Symphonia users, and hosted SaaS operation are outside the MVP.

## Goals

- Provide one inventory of connected provider playlists and library items with clear provenance.
- Recognize when provider-specific items likely represent the same recording.
- Let the user resolve ambiguity and preserve that decision.
- Copy a playlist between supported providers with a complete preview and result.
- Retain enough operation history to diagnose matching and provider failures.
- Establish extension points that make a third provider possible without changing the core domain.
- Run continuously on ordinary self-hosted infrastructure.

## Explicit non-goals

The MVP MUST NOT include:

- audio playback or a competing player experience;
- recommendations, discovery feeds, or AI-generated playlists;
- audio download, ripping, transcoding, streaming, or format management;
- multi-room audio or device control;
- social features or public profiles;
- multi-user tenancy or role-based administration;
- automatic bidirectional playlist synchronization;
- Home Assistant coupling inside the domain/application core or standalone composition;
- an assumption that similar titles imply identical recordings.

## Core user journeys

### Connect a provider

1. The user selects a provider.
2. Symphonia shows the provider's access basis, maturity/support classification, verified capabilities, requested permissions, and known limitations.
3. The user completes the provider's supported authorization flow.
4. Symphonia validates the grant and records a connection without exposing secrets.
5. The first import is scheduled and its progress is visible.

### Explore the library

1. The user sees connected providers and import freshness.
2. The user browses playlists grouped or filtered by provider connection.
3. Each item retains its original provider identity and shows its Symphonia recording link or resolution state.

### Resolve an ambiguous track

1. The user opens the unresolved-items queue.
2. Symphonia displays source metadata, candidates, confidence classification, and evidence.
3. The user selects a candidate, declares the item distinct, defers it, or marks it unresolvable.
4. Symphonia records the decision, actor, time, evidence context, and algorithm version.
5. Future operations reuse the decision unless the user revokes it or the provider identity becomes invalid.

### Copy a playlist

1. The user selects a source playlist and target connection.
2. Symphonia captures the source version and creates a dry-run plan.
3. The plan shows ordered matches, duplicates, ambiguous/unmatched/unavailable items, target capability constraints, and expected writes.
4. The user resolves blockers and chooses an explicit unresolved-item policy.
5. Symphonia executes the accepted plan safely.
6. The user sees the target playlist, item-level results, retries, omissions, and recovery actions.

### Diagnose an operation

1. The user opens operation history.
2. Symphonia shows status, timing, source and target, source version, plan version, checkpoints, provider calls summarized without secrets, and item-level outcomes.
3. The user can retry only the recoverable work or start a new plan when the source changed.

## MVP requirements

### Product and account

- **SYM-PROD-001:** The application core and standalone service MUST remain usable without Home Assistant, while the Home Assistant App is the primary supported deployment.
- **SYM-PROD-002:** The application MUST expose uncertainty and provider limitations before a provider write.
- **SYM-PROD-003:** The application MUST distinguish imported provider facts from user-authored decisions and Symphonia-derived data.
- **SYM-ACC-001:** The MVP MUST support one local Symphonia user.
- **SYM-ACC-002:** A provider connection MUST identify both the provider type and provider account; provider type alone is not an account identity.
- **SYM-ACC-003:** Disconnecting a provider MUST stop future provider calls and trigger the applicable provider-data retention workflow without erasing user-authored resolution history unless policy requires it.
- **SYM-ACC-004:** The UI MUST show connection health, last successful import, required user action, and granted functional access.
- **SYM-ACC-005:** The MVP Home Assistant Ingress management surface MUST be restricted to authenticated Home Assistant administrators.
- **SYM-ACC-006:** Before authorization, the UI MUST show whether access uses an official or reverse-engineered contract, adapter maturity/support level, required external dependencies, credential type, and expected reauthorization behavior.

### Unified library

- **SYM-LIB-001:** Every imported object MUST retain provider type, provider connection, provider object identifier, source timestamps when available, import time, and raw-data freshness metadata.
- **SYM-LIB-002:** The system MUST represent a recording independently from its provider representations.
- **SYM-LIB-003:** The system MUST preserve playlist order and repeated entries during import.
- **SYM-LIB-004:** Provider deletion or disappearance MUST be represented as availability state; it MUST NOT silently delete the independent recording or audit history.
- **SYM-LIB-005:** The UI MUST allow playlists to be filtered by provider connection and MUST NOT imply that an imported provider playlist is Symphonia-owned.
- **SYM-LIB-006:** The system SHOULD import the connected account's saved or liked tracks when the provider exposes that collection through an approved API.

### Identity resolution

- **SYM-MATCH-001:** Each provider track representation MUST be in exactly one resolution state: `resolved`, `ambiguous`, `unmatched`, `deferred`, or `invalid`.
- **SYM-MATCH-002:** A resolution MUST record its origin (`automatic` or `manual`) and the evidence and resolver version used.
- **SYM-MATCH-003:** Automatic matching MUST NOT rely on normalized title alone.
- **SYM-MATCH-004:** Matching MUST preserve distinctions between live, studio, cover, remix, edit, acoustic, remastered, clean, explicit, and other known version indicators when evidence permits.
- **SYM-MATCH-005:** The user MUST be able to accept a candidate, reject a candidate pair, create a distinct recording, defer, or revoke a prior manual resolution.
- **SYM-MATCH-006:** Manual acceptance and rejection decisions MUST be reused in later imports, copy plans, and sync plans until revoked or invalidated with an explanation.
- **SYM-MATCH-007:** A confidence label MUST be accompanied by human-readable evidence; a numeric score alone is insufficient.
- **SYM-MATCH-008:** Thresholds and scoring algorithms MUST remain versioned implementation policy and are not defined by this baseline.

### Playlist copy

- **SYM-PL-001:** Copy MUST be modeled as a finite operation, not as a continuing relationship.
- **SYM-PL-002:** Every copy MUST produce a non-mutating plan tied to a captured source playlist version or snapshot.
- **SYM-PL-003:** A plan MUST report every source entry as `ready`, `ambiguous`, `unmatched`, `unsupported`, `unavailable`, or `invalid` before execution.
- **SYM-PL-004:** Execution MUST require an explicit policy for non-ready entries; the MVP default policy is an open question.
- **SYM-PL-005:** Copy MUST preserve relative order and duplicate occurrences among entries that are written, subject to declared target capabilities.
- **SYM-PL-006:** Copy execution MUST have a stable idempotency key and MUST reconcile target state before repeating an uncertain provider write.
- **SYM-PL-007:** A source change after planning MUST be visible. The system MUST either require re-planning or explicitly execute the captured plan; it MUST NOT silently mix versions.
- **SYM-PL-008:** A copy result MUST include the created or selected target, outcome for every source entry, provider errors, and whether safe retry is possible.
- **SYM-PL-009:** Destructive overwrite of an existing target playlist MUST NOT be an implicit copy behavior.

### Operation history

- **SYM-PROD-004:** Imports, match-resolution changes, copy plans, copy executions, and future sync runs MUST be attributable and timestamped.
- **SYM-PROD-005:** The MVP MUST expose operation state and item-level failures in the UI.
- **SYM-PROD-006:** User-facing errors MUST say whether the operation is retrying, needs user action, partially succeeded, or permanently failed.

## MVP boundary

The first useful release is complete when one local user can:

- configure one Spotify connection and one validated Google/YouTube connection;
- authenticate with supported provider flows;
- import supported library collections and owned/followed playlists;
- browse provider playlists and their freshness;
- resolve track identities automatically where safe and manually where needed;
- preview and execute a copy in each direction only where the target adapter declares all required capabilities;
- inspect basic operation history; and
- deploy, upgrade, back up, restore, and rotate provider credentials using documented procedures.

The wording “validated Google/YouTube connection” is deliberate. Symmetric **YouTube Music** library access is not yet proven through an official API; see [provider research](../providers/provider-research.md). If official feasibility fails, the owner must revise the MVP rather than silently adopting a reverse-engineered API.

## Future scope

- Persistent one-way, add-only, and bidirectional playlist synchronization.
- Symphonia-owned logical playlists if the ownership RFC selects that model.
- Apple Music, Plex/Plexamp, Navidrome, and other adapters.
- Multiple accounts per provider in the UI.
- Home Assistant entities, actions, and events over a stable Symphonia API.
- More complete album, artist, release, and musical-work modeling.
- Export/import of user-authored mappings and operation history.

Future scope is not permission to build these items into the MVP.

## Product success measures

Targets require real-provider feasibility testing before numeric thresholds are accepted. The MVP MUST at least measure:

- imported items and playlists per connection;
- resolution-state counts and the proportion automatically resolved;
- manual-resolution reuse;
- copy plan versus execution outcomes;
- provider request, throttle, retry, and failure counts; and
- time since last successful import and operation completion.

No response-time, matching-accuracy, or scale target is accepted yet; the test corpus and expected homelab library sizes are open questions.
