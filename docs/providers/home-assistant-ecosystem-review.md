# Home Assistant music ecosystem review

**Status:** research snapshot and design input, not a dependency or scope decision
**Reviewed:** 2026-09-20
**Source policy:** project documentation and current source were inspected in addition to official provider documentation; revalidate before implementation

## Purpose

This review asks what Symphonia can learn from existing Home Assistant music projects without assuming that their goals, guarantees, or risk tolerance match ours. It complements the official-API-only [provider research](provider-research.md).

The strongest precedent is Music Assistant: a separate service/App owns the music domain and a comparatively thin Home Assistant integration exposes native surfaces. Existing YouTube Music projects reduce uncertainty about technical access, but they also provide direct evidence that authentication and API stability are the central risks rather than solved details.

## Executive conclusions

1. **Keep the App/service as the system of record and the Home Assistant integration thin.** The [Music Assistant integration](https://www.home-assistant.io/integrations/music_assistant/) connects Home Assistant to a separately running server and exposes selected entities/actions. This validates Symphonia's accepted deployment direction without requiring Symphonia to become a playback system.
2. **Adopt a manifest plus effective-capability model.** Music Assistant provider implementations declare features and support multiple provider instances. Symphonia needs the same extensibility, but with more granular, runtime capability descriptors because copy and sync require stronger guarantees than playback and browsing.
3. **Reuse Home Assistant's OAuth conventions where possible, not its provider domain logic.** The official [Spotify integration](https://www.home-assistant.io/integrations/spotify) demonstrates bring-your-own application credentials, multiple accounts, and Home Assistant's external OAuth callback. A companion integration could potentially broker authorization for the App, but this is a spike candidate rather than an accepted design.
4. **Treat unofficial YouTube Music access as a distinct product mode.** Music Assistant and `ytube_music_player` demonstrate useful access through `ytmusicapi`, browser cookies, internal endpoints, and proof-of-origin tokens. They do not turn that surface into a supported Google API. An unofficial adapter would need explicit opt-in, health warnings, separate release gating, and no promise of symmetric copy/sync.
5. **Apple Music is a credible future official-library adapter.** Apple's official API documents library reads, catalog/library search, ISRC, playlist creation, and adding tracks. It does not document playlist-track removal, so new-playlist copy is more plausible than mirror sync. Its user-token acquisition and Home Assistant callback story still require a spike.
6. **Do not inherit playback-first shortcuts.** Symphonia must preserve unavailable entries, expose ambiguous matches, prove pagination completeness, and retain auditable user decisions even where an existing playback product can skip, merge, cap, or rescan data.

## Projects reviewed

| Project | What it establishes | Useful pattern for Symphonia | Boundary or warning |
| --- | --- | --- | --- |
| [Home Assistant Spotify](https://www.home-assistant.io/integrations/spotify) | A maintained Home Assistant integration can use application credentials, the HA external OAuth callback, and multiple account entries | Native config flow, reauthentication, callback and credential UX | It is a playback/media-browser integration, not a cross-provider library system |
| [Home Assistant Music Assistant integration](https://www.home-assistant.io/integrations/music_assistant/) | Home Assistant can discover and connect to a separate music server running as an App or container | Service owns domain; integration exposes bounded native actions/entities over an API | Installing an App and installing an integration remain separate lifecycle steps |
| [Music Assistant server](https://github.com/music-assistant/server) | Provider plugins, feature declarations, multiple instances, a normalized internal library, provider mappings, scheduled sync, and versioned SQLite migrations work at real scale | Provider manifest, connection instance, normalized mapping graph, scheduled imports | Playback requirements and automatic merging are not Symphonia requirements |
| [Music Assistant Spotify provider](https://www.music-assistant.io/music-providers/spotify/) | Spotify library/search support and multiple accounts are operationally feasible | Capability probing, account-specific source selection, OAuth lifecycle | Playback engines and their policy/terms trade-offs are out of scope |
| [Music Assistant YouTube Music provider](https://www.music-assistant.io/music-providers/youtube-music/) | Reading a YT Music library/search surface is technically feasible through private web behavior | Isolate the adapter, identify provider-instance-scoped IDs, expose reauthentication health | The project explicitly says there is no official API; cookies expire and a PO-token sidecar is required |
| [`ytube_music_player`](https://github.com/KoljaWindeler/ytube_music_player) | A Home Assistant custom integration can browse/play YT Music via `ytmusicapi` | Additional implementation evidence and failure cases | Its current [browser-auth guide](https://github.com/KoljaWindeler/ytube_music_player/blob/main/QUICK_START_BROWSER_AUTH.md) says OAuth is broken and asks users to export authenticated browser headers |
| [Music Assistant Apple Music provider](https://www.music-assistant.io/music-providers/apple-music/) | Apple libraries and catalog can be represented behind a provider abstraction | Separate catalog/library identifiers and object-level editability | Its playback/auth workarounds are not evidence that every flow is officially supported for Symphonia |
| [`apple-music-custom`](https://github.com/Hackashaq666/apple-music-custom) | A community integration can pair a local companion server with a Home Assistant media-player integration | Another example of a server/integration boundary | It controls the Music app on a macOS host; it is not a cloud-library interoperability adapter |

No source code has been selected for reuse. Any future reuse proposal must review the exact dependency version, license, security posture, transitive dependencies, and whether importing that implementation would couple Symphonia to playback behavior.

The review identified official Home Assistant integrations for Spotify and Music Assistant, but did not identify official direct integrations for YouTube Music or Apple Music. The direct examples above are Music Assistant providers or community/HACS integrations, not official Home Assistant Core integrations. Their existence is implementation evidence, not a platform support guarantee.

## Architecture lessons from Music Assistant

### Server plus integration is the right split

The official Home Assistant integration requires a Music Assistant server and can connect to a server hosted as an App or separate container. That closely matches Symphonia's intended shape:

```text
Home Assistant integration  →  versioned local API  →  Symphonia App/service
native actions/entities                              domain, jobs, adapters, data
```

The integration should remain replaceable and unavailable independently. It must not read the App database or become the only way to run provider imports and copies.

### Provider manifests and instances are worth adopting

Music Assistant providers have manifests, declared features, configuration, and an instance identity. Its current [YouTube Music manifest](https://github.com/music-assistant/server/blob/dev/music_assistant/providers/ytmusic/manifest.json), for example, labels the provider `beta`, declares `multi_instance`, and pins `ytmusicapi`.

Symphonia should adopt the concepts, but strengthen them:

- a manifest describes static adapter identity, provenance, official/unofficial status, version, configuration schema, and declared upper-bound capabilities;
- a provider connection describes the actual account and its scopes, market, health, and probed capabilities;
- an individual playlist or item can further restrict an operation, such as Apple's `canEdit=false`; and
- workflows are enabled only from the intersection of adapter, connection, object, and current-health capabilities.

A provider object identity may need `(adapter kind, provider instance/connection namespace, object type, provider object ID)`. Music Assistant's current YouTube Music source explicitly notes that some personal playlist IDs are not unique across instances. Symphonia must never assume that an upstream ID is globally unique merely because it looks stable.

### Provider mappings validate the representation graph

Music Assistant's [Music Controller](https://github.com/music-assistant/server/tree/dev/music_assistant/controllers/music) aggregates providers into an internal SQLite library and uses provider mappings to relate internal items to provider items. This supports Symphonia's decision to keep provider representations separate from provider-independent recordings.

The semantic difference matters: Music Assistant may automatically merge items to make playback convenient. Symphonia's mappings influence external writes and therefore require stored evidence, confidence, negative decisions, resolver versions, and manual review. We can borrow the shape, not silent match policy.

### Migration recovery must reflect irrecoverable local decisions

Music Assistant's controller documentation records a real divergence between stable and development schema-version histories. This is useful evidence for a per-migration ledger and cross-channel upgrade tests.

Its ability to fall back to a fresh library database after a failed migration is not generally safe for Symphonia. Provider data may be re-importable, but manual identity decisions, accepted plans, job checkpoints, and audit history are not. Restore or migration failure must stop writes and lead to explicit recovery, not silently discard locally owned state.

## Provider-specific findings

### Spotify

The official Home Assistant Spotify integration reduces OAuth uncertainty. It instructs self-hosters to create a Spotify application with `https://my.home-assistant.io/redirect/oauth`, or `<HOME_ASSISTANT_URL>/auth/external/callback` when My Home Assistant is disabled. Home Assistant's [Application Credentials platform](https://developers.home-assistant.io/docs/core/platform/application_credentials/) supplies local client credentials, OAuth/PKCE helpers, token refresh, and reauthentication patterns.

This yields two candidates for the OAuth spike:

1. **Direct App flow:** Symphonia owns the callback, token exchange, refresh, and storage. This keeps the provider adapter self-contained but must solve public callback reachability and must not expose an unauthenticated management port.
2. **Companion-integration authorization broker:** a minimal custom integration uses Home Assistant's config flow/application credentials and transfers an opaque, one-use connection grant to the App over an authenticated local contract. This reuses HA callback UX but creates a token-ownership, lifecycle, backup, and versioning boundary that must be threat-modeled.

The companion integration cannot simply be assumed to make OAuth free: an App does not automatically inherit Home Assistant Core's integration helpers.

### YouTube Music

The current Music Assistant provider is unusually valuable as negative as well as positive evidence:

- its [documentation](https://www.music-assistant.io/music-providers/youtube-music/) explicitly labels the implementation best-effort because YouTube offers no official API for this data/stream surface;
- setup uses a browser cookie and a separate proof-of-origin token generator;
- its [manifest](https://github.com/music-assistant/server/blob/dev/music_assistant/providers/ytmusic/manifest.json) labels the provider beta and depends on `ytmusicapi`;
- its [source](https://github.com/music-assistant/server/blob/dev/music_assistant/providers/ytmusic/__init__.py) namespaces personal playlist IDs by instance, caps some dynamic playlists, lacks paging for playlist tracks, skips unavailable tracks, and currently advertises read/search features rather than playlist-write features; and
- `ytube_music_player` independently documents cookie expiry and a broken OAuth path.

This changes the uncertainty from “is library access technically possible?” to “can Symphonia responsibly support a moving, unofficial authentication and data contract?” The answer may be yes for an explicitly experimental adapter, but not as an invisible fallback for the official YouTube Data API.

Minimum conditions for such an adapter would be:

- an `unofficial_reverse_engineered` access basis, honest maturity/product-support labels, and explicit user acknowledgement;
- no request for a user's primary Google-account cookie without a clear threat model and deletion path;
- dependency and upstream-contract health surfaced in the UI;
- preserved unavailable/unknown entries and explicit incompleteness when paging or caps are uncertain;
- writes disabled until independently proven by contract tests and dedicated accounts; and
- ability to disable/release the adapter independently from official providers.

### Apple Music

Apple's official [Apple Music API](https://developer.apple.com/documentation/applemusicapi/) can read personal library resources and the catalog. The API documents [all library songs](https://developer.apple.com/documentation/applemusicapi/get-all-library-songs), paginated responses, catalog/library search, song ISRC, [new library playlist creation](https://developer.apple.com/documentation/applemusicapi/create-a-new-library-playlist), and [adding tracks](https://developer.apple.com/documentation/applemusicapi/add-tracks-to-a-library-playlist).

Important limitations for Symphonia:

- personalized calls require both a developer token and a Music User Token; [MusicKit user authentication](https://developer.apple.com/documentation/applemusicapi/user-authentication-for-musickit) must be validated in a self-hosted web/App context;
- library song IDs and catalog song IDs are distinct; both must be retained when present;
- playlist editability is object-specific (`canEdit`), so connection-wide “playlist write” is insufficient;
- Apple documents create and append operations, but the reviewed API surface did not identify an operation to remove playlist entries; and
- Music Assistant reports manual reauthentication and direct-port/cookie fallbacks, which are implementation evidence but not an official contract Symphonia should inherit.

Therefore Apple Music looks promising for future import and one-time copy-to-new-playlist, but not for strict mirror or bidirectional sync until removal/reorder and authentication are proven.

## Security lessons

A 2026 [Music Assistant security advisory](https://github.com/music-assistant/server/security/advisories/GHSA-7jcc-p6xr-835j) described an unauthenticated direct service port combined with user-controlled filesystem paths and root execution. Symphonia does not need a filesystem music provider, but the boundary lessons apply:

- Ingress authentication does not protect a separately exposed App port.
- A callback listener must expose only the minimum callback surface or have its own authentication; it must never make the management API anonymously reachable.
- Provider IDs, playlist names, URIs, imported metadata, and callback parameters are data, never filesystem paths, import names, executable schemes, or unrestricted outbound URLs.
- The container should run as a non-root user where the App platform permits and have no host/config media mounts without a specific requirement.
- URI schemes, callback destinations, redirect targets, and adapter-controlled outbound hosts need allowlists and canonical validation.

## Adopt, adapt, and avoid

### Adopt

- App/service plus thin Home Assistant integration.
- Provider manifests, multiple connection instances, and declared features.
- Internal provider-representation mappings and versioned migrations.
- Native Home Assistant application-credential/config-flow patterns where a companion integration genuinely owns that boundary.

### Adapt

- Replace coarse provider features with operation- and object-level effective capabilities.
- Replace playback-friendly automatic merging with evidence-backed, reversible identity links.
- Replace “rescan after failure” with recovery that protects user-authored state.
- Treat provider quality labels as a first-class support tier visible in planning and diagnostics.

### Avoid

- Treating unofficial access as equivalent to an official API.
- Exporting full browser cookies as a normal setup path without an explicit experimental security model.
- Skipping unavailable tracks or returning capped lists as if complete.
- Exposing a direct unauthenticated port merely to make OAuth convenient.
- Letting provider values influence local file paths, arbitrary URI schemes, redirects, or code/module loading.

## Design consequences for the next RFCs

This review does not accept a dependency or new provider into the MVP. It narrows the next evidence work:

1. Extend the provider manifest RFC with independent access-basis, maturity, and product-support classifications so, for example, unofficial-but-mature and official-but-experimental are not conflated.
2. Make capabilities an intersection of adapter, connection, object, and live health—not provider-wide booleans.
3. Include provider instance/connection namespace and object type in external-identity analysis.
4. Compare direct App OAuth with a minimal companion-integration authorization broker in the Home Assistant OAuth spike.
5. Add an Apple Music test-account spike as a future-provider candidate, focusing on Music User Token acquisition, catalog/library IDs, `canEdit`, playlist append, and absence of remove/reorder.
6. Require completeness markers for every import/list operation and preserve unavailable entries.
7. Threat-model every directly exposed App listener and prevent provider-controlled values from acquiring filesystem or executable semantics.
