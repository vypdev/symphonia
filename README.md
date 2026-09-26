# Symphonia

Symphonia is a self-hosted, provider-independent music library hub, distributed primarily as a Supervisor-managed Home Assistant App. It is intended to help a person understand, move, and eventually synchronize their music across services such as Spotify and YouTube without treating any one provider as the source of the domain model.

> Your music library belongs to you. Providers are places where representations of that music happen to exist.

Symphonia is a library-management and interoperability project, not a new music player. Playback, recommendations, social features, transcoding, and multi-room audio are outside the initial scope. Its domain and application core remain independent of Home Assistant so the service can also run and be tested standalone; the deployment and integration pattern follows `vypdev/homeassistant-gateway`.

## Project status

**Implementation foundation stage. Provider adapters, durable import/copy execution, and an experimental Home Assistant App metadata scaffold exist; no published App image, complete UI, or OAuth flow is available yet.**

The current work combines a reviewable source of truth with the first owner-approved, dependency-free domain/persistence slice. Official provider feasibility still needs validation: Google's public YouTube Data API can manage YouTube video playlists, but the research performed for this specification did not identify an official API exposing the complete YouTube Music library model.

### Current adapter boundaries

- Spotify: official playlist reads plus confirmed playlist creation and entry append operations, subject to connection capabilities and provider policy.
- YouTube Data API: official video-playlist reads only; this is deliberately not represented as YouTube Music.
- Apple Music: experimental official library-playlist reads using separate developer and Music User Token inputs; writes and OAuth wiring remain out of scope until their feasibility gates are closed.

All adapters expose normalized identities and preserve unavailable/duplicate occurrences. Provider credentials are injected behind ports and are not accepted through App options, logs, or ordinary operation payloads.

## Documentation

Start with the [documentation map](docs/README.md). The horizontal specifications define shared product and architecture rules; the [SDD standard](specs/README.md) and [capability catalog](specs/CATALOG.md) turn those rules into reviewable vertical implementation contracts.

| Area | Source of truth |
| --- | --- |
| Capability readiness and implementation contracts | [SDD catalog](specs/CATALOG.md) |
| SDD lifecycle, template, and readiness gate | [SDD standard](specs/README.md) |
| Vision, scope, journeys, requirements | [Product specification](docs/product/product-specification.md) |
| Home Assistant-native UI and component contract | [UI specification](docs/product/home-assistant-ui-specification.md) and [UI foundation SDD](specs/home-assistant-native-ui.md) |
| Vocabulary, entities, identity, playlists | [Domain model](docs/domain/domain-model.md) |
| System boundaries and operational qualities | [Architecture](docs/architecture/system-architecture.md) |
| Provider contract and capability semantics | [Provider specification](docs/providers/provider-specification.md) |
| Current official-provider evidence | [Provider research](docs/providers/provider-research.md) |
| Existing Home Assistant music projects and design lessons | [Ecosystem review](docs/providers/home-assistant-ecosystem-review.md) |
| Engineering and testing workflow | [Development specification](docs/development/development-specification.md) |
| Decisions already accepted | [Architecture decisions](docs/decisions/README.md) |
| Risks and unresolved choices | [Open questions](docs/open-questions.md) |

## Product shape

The intended first useful workflow is:

1. A local user connects provider accounts.
2. Symphonia imports provider playlists and track representations without losing provenance.
3. It resolves provider tracks to provider-independent recordings, surfacing uncertainty rather than hiding it.
4. The user reviews unresolved items and records durable manual decisions.
5. The user previews and executes a one-time playlist copy.
6. The operation history explains every match, omission, provider write, retry, and failure.

Persistent synchronization follows only after copy semantics and official provider feasibility are understood.

## Contributing during specification

Use requirement identifiers in issues, SDDs, tests, and future commits. Material implementation work starts from the applicable cataloged SDD and its numeric verification budget. A change to accepted behavior must update the relevant horizontal specification and, when it changes an architectural decision, add or supersede an ADR. Do not infer a decision from an open question, and do not start production implementation until the SDD is ready and the owner explicitly approves it.

Before opening a change, run `make verify`. It checks the SDD/catalog links and
traceability, patch whitespace, and the offline test suite without provider
accounts, Home Assistant, or network access.

The two current evidence spikes can be run independently: `make spike-storage`
exercises restart/lease recovery and SQLite backup validation, while the
[OAuth callback spike](docs/development/oauth-callback-spike.md) documents the
direct App-owned callback boundary. Both are research evidence, not published
production endpoints.
