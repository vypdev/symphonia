# ADR 0001: Provider-independent recording domain

- **Status:** accepted
- **Date:** 2026-09-20

## Context

Symphonia must relate music found at multiple providers. If core identities and workflows are shaped around Spotify IDs or YouTube videos, adding providers will leak provider assumptions into matching, playlists, persistence, and UI. Similar titles are also insufficient: a musical work can have covers, live performances, remixes, edits, and remasters.

ISRC identifies a recording rather than an abstract composition, and even ISRC must be treated as evidence because provider metadata can be absent or inconsistent.

## Decision

Symphonia owns provider-independent domain identities. The MVP's primary matchable entity is `Recording` (shown to users as a Symphonia track). Provider tracks are representations linked to a recording by an explicit, evidenced identity link.

`MusicalWork`, `Recording`, `Release`, and `ProviderTrack` are distinct concepts. Musical-work canonicalization is not required in the MVP, but the model must not collapse different recordings merely because they represent the same work.

Provider APIs are infrastructure adapters behind capability-aware ports. Provider IDs remain opaque external identities and never become Symphonia IDs.

## Alternatives considered

### Use Spotify objects as the core model

Rejected because Spotify would become a permanent dependency and other providers would be forced into Spotify semantics.

### Use the lowest common provider fields as the domain

Rejected because it discards important provenance and cannot express uncertainty, version distinctions, or richer providers.

### Match musical works rather than recordings

Rejected for the MVP because playlist interoperability normally needs a specific playable recording/version, not merely a composition.

### Treat every provider track as unrelated

Rejected because copying, synchronization, and reusable manual resolution require cross-provider identity.

## Consequences

Positive:

- providers can be replaced and extended;
- manual decisions and operation history survive provider changes;
- ambiguity and contradictory evidence can be represented;
- covers and versions need not be conflated.

Trade-offs:

- import requires normalization and identity resolution;
- canonical metadata needs provenance/merge rules;
- provider-specific data must be stored alongside, not forced into, the core entity;
- migrations may be needed as recording/release/work knowledge improves.

