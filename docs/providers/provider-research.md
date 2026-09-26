# Provider and platform research

**Status:** research snapshot, not an architectural decision
**Reviewed:** 2026-09-22
**Source policy:** official documentation only; revalidate before implementation and every release

## How to read this document

This snapshot separates what Symphonia needs from what an official API documents. It does not prove behavior for a particular account, market, application mode, or Home Assistant network setup. A live feasibility spike is required before either provider adapter is committed to the MVP.

Existing Home Assistant and community implementations are reviewed separately in [Home Assistant music ecosystem review](home-assistant-ecosystem-review.md). They provide valuable implementation evidence but do not replace an official provider contract.

## 2026-09-22 verification update

The official references were rechecked before the next design pass. This is a
documentation refresh, not a completed live-provider feasibility spike.

| Provider/platform | Reconfirmed official evidence | Consequence for Symphonia |
| --- | --- | --- |
| Spotify | Playlist creation remains a separate empty-playlist operation; playlist item insertion accepts at most 100 items per request; the create operation defaults to public unless the request explicitly selects private visibility and has the required scope. | Keep target creation, visibility, batching, and checkpointing as separate capability decisions. The adapter must default to the product's safe private policy rather than inheriting the API default. |
| Spotify authorization | Access tokens remain short-lived and the current refresh-token guidance documents a six-month lifetime for Developer Dashboard apps. | Reauthorization is a normal durable state and must be visible before an import or write is dispatched. |
| YouTube Data API | The official surface models playlists as collections of videos; playlist-item insertion is an OAuth-protected write and the documented default quota is 10,000 units/day for most endpoints, with writes commonly costing 50 units. | The official adapter can be called YouTube Data, not YouTube Music. Search and write budgets must be planned explicitly; a playlist/video ID is not a recording identity. |
| Apple Music | The official API exposes a personal iCloud Music Library, playlist reads, playlist creation, and adding tracks, using a developer token plus Music User Token. | Apple remains a future/contingency provider. Its token and origin lifecycle still require a dedicated feasibility spike before MVP promotion. |
| Home Assistant Apps | Ingress is the authenticated UI boundary, requires the App to allow only the Supervisor ingress source, and exposes the ingress path through a request header. | The App can keep management routes Ingress-only, but this does not solve provider OAuth callback ownership or token storage. |

These checks reinforce the existing conclusion: the repository may prepare
official Spotify and ordinary YouTube adapter contracts, but it must not claim
full YouTube Music library parity or silently use an unofficial endpoint.

Legend:

- **Documented**: an official current page describes the needed primitive.
- **Partial**: a related primitive exists but does not establish Symphonia's full semantics.
- **Not documented**: no official support was identified in the reviewed sources; this is not proof that no private API exists.
- **Unknown**: official documentation is insufficient; test without relying on undocumented behavior.

## Capability needs versus official support

| Need | Spotify Web API | YouTube Data API v3 | MVP consequence |
| --- | --- | --- | --- |
| User OAuth and unattended refresh | Documented: authorization-code flows; current docs state 1-hour access tokens and 6-month refresh-token lifetime | Documented: OAuth 2.0 web-server flow with offline access/refresh token | Reauthorization states are normal operations, not exceptional crashes |
| Read account playlists | Documented: current user's owned/followed playlists; scopes affect private/collaborative results | Documented: playlists for authenticated user with `mine=true` | Both can list some account playlists; collection semantics differ |
| Read ordered playlist entries | Documented | Documented for YouTube video `playlistItem` resources | YouTube entries are videos, not documented music-catalog recordings |
| Create playlist | Documented | Documented | Both have a creation primitive |
| Add entries | Documented, up to 100 URIs per documented request | Documented, one resource insertion operation; current cost 50 quota units | Batch/checkpoint and cost models differ materially |
| Remove/reorder/replace | Documented Spotify playlist operations, subject to current endpoint availability/mode | Insert/update/delete playlist-item methods exist; exact duplicate/reorder behavior needs spike | Do not advertise sync from surface similarity alone |
| Saved/liked track library | Documented saved-track endpoints and newer generic library operations | Partial: YouTube exposes a special liked-videos playlist; equivalence to YouTube Music liked songs/library is not documented | “Library” must stay provider-specific until semantics are verified |
| Music catalog search | Documented track search, including `isrc` query filter | Partial: generic YouTube video/channel/playlist search, not a documented YouTube Music catalog search | Cross-provider YouTube matching is the largest feasibility risk |
| ISRC | Documented in Spotify track `external_ids` and search filter | Not documented on YouTube `video`/`playlistItem` resources | YouTube candidates need weaker evidence or another approved source |
| Album/artist/duration metadata | Documented music entities and track duration | Partial: video title/channel/duration; not equivalent to recording/release metadata | Normalization must show evidence quality |
| Revision/change token | Spotify playlist `snapshot_id` documented | ETags exist generally; playlist-change attribution semantics need spike | Polling and stored baselines are still required |
| Playlist webhooks | Not identified in reviewed official Web API docs | No playlist-change push contract identified; push notifications cover channel-resource activity, not a general playlist sync feed | Assume polling until proven otherwise |
| Rate/quota model | Rolling 30-second application limit; 429 and `Retry-After`; exact limit varies by mode | Default quotas documented, including a search-query bucket and general daily units; operations have individual cost | Planner/scheduler must be provider-aware |
| Full YouTube Music library model | N/A | **Not documented.** Reviewed public API is YouTube Data API, centered on videos/channels/playlists | Do not label the official adapter “full YouTube Music” without evidence |

## Spotify Web API

### Verified useful primitives

- [Get Current User's Playlists](https://developer.spotify.com/documentation/web-api/reference/get-a-list-of-current-users-playlists) returns owned or followed playlists and exposes `snapshot_id`; private/collaborative visibility depends on scopes.
- [Create Playlist](https://developer.spotify.com/documentation/web-api/reference/create-playlist) and [Add Items to Playlist](https://developer.spotify.com/documentation/web-api/reference/add-items-to-playlist) support the core target-write workflow. The add endpoint documents a maximum of 100 items per request.
- [Search for Item](https://developer.spotify.com/documentation/web-api/reference/search) supports track searches and an `isrc` field filter. Track results include `external_ids.isrc` where known.
- [Get Track](https://developer.spotify.com/documentation/web-api/reference/get-track) documents duration, artists, album context, and known external IDs including ISRC.
- Spotify's [playlist concepts](https://developer.spotify.com/documentation/web-api/concepts/playlists) document how scopes affect owned/followed, private, and collaborative playlists.

### Authorization and access constraints

- Spotify recommends authorization code for a long-running confidential web service and PKCE when a client secret cannot be stored; see [Authorization](https://developer.spotify.com/documentation/web-api/concepts/authorization).
- Current [refresh-token documentation](https://developer.spotify.com/documentation/web-api/tutorials/refreshing-tokens) states that Developer Dashboard refresh tokens last six months and refreshing access does not extend that lifetime. Symphonia must expect scheduled user reauthorization unless policy changes.
- Spotify's February 2026 [developer-access update](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security) states that Development Mode requires the app owner to have Premium, limits a developer to one Client ID and an app to five authorized users, and limits new Development Mode apps to a smaller endpoint set. The March 9 update postponed endpoint-access changes for existing integrations but not Premium/user/client limits.
- The [February 2026 migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide) and [changelog](https://developer.spotify.com/documentation/web-api/references/changes/february-2026) must be checked against every endpoint selected for the adapter. Development Mode is plausible for a personal install but is not a stable basis for a hosted multi-user product.
- Spotify's [rate-limit documentation](https://developer.spotify.com/documentation/web-api/concepts/rate-limits) describes an application-wide rolling 30-second window, mode-dependent limits, endpoint exceptions, and 429 responses. Exact numeric limits are not generally published; the adapter must learn from responses.

### Spotify risks to validate

1. Every required read/write endpoint is available to a newly created September 2026 Development Mode application.
2. A self-hoster can register the callback URL that the Home Assistant App flow requires.
3. Saved-library and playlist content can be stored/used as Symphonia proposes under current developer terms.
4. Snapshot and response behavior is sufficient to reconcile timeouts and repeated entries.
5. Six-month refresh-token expiry gives adequate warning and recovery UX.

## YouTube and YouTube Music

### What the official API documents

- The [YouTube Data API reference](https://developers.google.com/youtube/v3/docs) manages YouTube resources such as videos, channels, playlists, and playlist items.
- Official [playlist guidance](https://developers.google.com/youtube/v3/guides/implementation/playlists) documents `playlists.list` with `mine=true` for the authenticated user's playlists.
- [Playlists](https://developers.google.com/youtube/v3/docs/playlists) can be listed, inserted, updated, and deleted.
- [Playlist items](https://developers.google.com/youtube/v3/docs/playlistItems) can be listed, inserted, updated, and deleted. A playlist item points to a resource such as a YouTube video.
- [PlaylistItems: list](https://developers.google.com/youtube/v3/docs/playlistItems/list) currently costs one general quota unit per call; [PlaylistItems: insert](https://developers.google.com/youtube/v3/docs/playlistItems/insert) currently costs 50 general quota units.
- [Search: list](https://developers.google.com/youtube/v3/docs/search/list) is generic YouTube search. Current documentation describes a default search-query allocation of 100 calls/day in a dedicated bucket; [quota guidance](https://developers.google.com/youtube/v3/getting-started#quota) describes a default 10,000-unit daily allocation for other endpoints, subject to change and extension review.
- Google's [web-server OAuth guide](https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps) documents offline access and refresh tokens for unattended calls.

### What is not established

The reviewed official developer documentation did not identify a public **YouTube Music API** that exposes the complete YouTube Music library, song catalog identity, liked songs, albums, or ISRC metadata. The YouTube Data API can create and modify playlists of videos, but official documentation does not promise that:

- every YouTube Music playlist appears with identical behavior through `playlists.list`;
- a YouTube video corresponds to exactly one musical recording;
- YouTube Music “songs,” uploads, liked songs, and ordinary liked videos share one API model;
- music-specific catalog IDs, album editions, artist credits, explicitness, or ISRC are exposed; or
- writes through the Data API reproduce all YouTube Music UI semantics.

This absence is an inference from the official surface reviewed on the date above, not a claim about Google's private APIs. Libraries such as `ytmusicapi` use unofficial/reverse-engineered endpoints and therefore have materially different stability, authentication, policy, and maintenance risk. Adopting one requires an explicit ADR and user opt-in; it is not an implicit fallback.

### Policy and quota constraints

- [YouTube API Services Developer Policies](https://developers.google.com/youtube/terms/developer-policies) require most stored Authorized API Data not otherwise exempted to be deleted or refreshed within 30 calendar days, and require cleanup after revocation/loss of authorization. Symphonia needs per-field provenance and refresh-by scheduling rather than indefinite raw-cache retention.
- Sensitive-scope production apps can require Google verification; [verification guidance](https://support.google.com/cloud/answer/13464321) and [app audience/user-cap guidance](https://support.google.com/cloud/answer/15549945) must be evaluated for a distributed self-hosted app whose users may bring their own OAuth project.
- Invalid requests also consume quota. Candidate search must be bounded, cached within policy, and planned against daily budgets.

### YouTube feasibility gates

Before “YouTube Music provider” becomes an accepted MVP promise, a spike using a dedicated test account MUST answer:

1. Which playlists created, followed, or edited in YouTube Music are visible through the official Data API?
2. Can they be copied in both directions with order and duplicates intact?
3. How are liked songs, uploads, unavailable videos, music videos, and topic-channel tracks represented?
4. What metadata can distinguish a label recording from a cover, live video, lyric video, edit, or user upload?
5. Are write results reflected in the YouTube Music client as users expect?
6. What OAuth scopes, verification mode, callback URLs, quota, and 30-day refresh behavior apply to a self-hosted install?

If official support is insufficient, owner decisions are required among narrowing the MVP to ordinary YouTube playlists, deferring Google/YouTube, or accepting a separately labeled unofficial adapter.

## Apple Music future-provider observations

Apple Music is outside the current MVP, but the ecosystem review identified a materially stronger official library surface than YouTube Music. It is therefore a useful future-provider or contingency candidate, not an accepted scope change.

### Documented useful primitives

- The official [Apple Music API overview](https://developer.apple.com/documentation/applemusicapi/) covers the Apple Music catalog and a user's personal iCloud Music Library, including playlist reads and authorized playlist modification.
- [Get All Library Songs](https://developer.apple.com/documentation/applemusicapi/get-all-library-songs) exposes paginated personal-library songs and may include a distinct `catalogId` alongside the library resource ID.
- Catalog [song attributes](https://developer.apple.com/documentation/applemusicapi/songs/attributes-data.dictionary) include ISRC, duration, artist, album, release date, explicitness, and other useful matching evidence. The Songs API also documents lookup of multiple catalog songs by ISRC.
- The API documents both catalog and [library search](https://developer.apple.com/documentation/applemusicapi/search-for-library-resources).
- [Create a New Library Playlist](https://developer.apple.com/documentation/applemusicapi/create-a-new-library-playlist) and [Add Tracks to a Library Playlist](https://developer.apple.com/documentation/applemusicapi/add-tracks-to-a-library-playlist) support a one-time copy-to-new-playlist workflow.
- Library playlists expose object-specific editability such as `canEdit`; provider support cannot be inferred from the account alone.

### Authorization and write limitations

- Personalized requests require a developer token and a Music User Token; see [User Authentication for MusicKit](https://developer.apple.com/documentation/applemusicapi/user-authentication-for-musickit). MusicKit manages user tokens on Apple platforms and the web, but a self-hosted Home Assistant App still needs a dedicated browser/origin/token-lifecycle spike.
- A MusicKit developer registration requires a media identifier and private key. Secret generation, storage, rotation, and the user experience for a distributed self-hosted project are unresolved.
- The reviewed official playlist surface documents creation and appending tracks. It did not identify a documented endpoint to remove or reorder playlist entries. Absence from the reviewed documentation is not proof of impossibility, but strict mirror/bidirectional sync MUST treat those capabilities as `unknown` or `unsupported` until proven.
- Library and catalog IDs are not interchangeable. An adapter needs to retain both and resolve the correct ID type for reads and writes.

### Apple feasibility gates

Before proposing Apple Music scope, a dedicated account spike MUST answer:

1. Can MusicKit on the Web acquire and renew a Music User Token reliably through Home Assistant Ingress without an unauthenticated direct management port?
2. Which user/developer secrets are device-, origin-, App-, or installation-specific, and what can safely survive backup/restore?
3. Are every-page library and playlist imports complete for purchased, uploaded, matched, subscription, and unavailable items?
4. Which resource ID type is required when creating a playlist or appending a catalog/library song?
5. How do `canEdit`, collaborative/shared playlists, storefront, and subscription state alter effective capabilities?
6. Is there any current official removal/reorder primitive, and if not, which copy/sync workflows remain honest?

## Home Assistant platform

Home Assistant is the primary deployment platform, not a music provider.

- [Home Assistant Apps](https://developers.home-assistant.io/docs/apps/) are Supervisor-managed container applications distributed through App repositories.
- [App configuration](https://developers.home-assistant.io/docs/apps/configuration/) documents `/data` persistent storage, startup types, architecture metadata, Ingress, App options, and backup modes.
- [App presentation/Ingress](https://developers.home-assistant.io/docs/apps/presentation/#ingress) documents the authenticated proxied UI boundary and Ingress base-path considerations.
- [Frontend design guidance](https://developers.home-assistant.io/docs/frontend/design/) identifies the official design portal as the maintained place to inspect reusable components, card states, light/dark comparisons, and Home Assistant wording.
- [Frontend architecture](https://developers.home-assistant.io/docs/frontend/architecture/) documents a web-component, panel, dialog, unidirectional-data-flow, and decentralized-routing architecture. This is useful reference evidence, not a requirement that an independently served App import the complete frontend.
- Home Assistant's [2026.4 component update](https://developers.home-assistant.io/blog/2026/03/25/frontend-component-updates-2026.4/) explicitly warns custom-card authors that built-in component APIs can change and recommends independent components. Symphonia applies that churn warning to its stronger iframe boundary and therefore mirrors public semantics/tokens through its own compatibility layer rather than depending on private bundles.
- Home Assistant's [2026.8 component/App update](https://developers.home-assistant.io/blog/2026/07/31/frontend-component-updates-2026.8/) documents safe-area handling and propagated inset values for custom panels and App iframes. Supported-version behavior still requires `RG-006` rather than assuming every installed Home Assistant version exposes the same context.
- The current official [`ha-card` source](https://github.com/home-assistant/frontend/blob/dev/src/components/ha-card.ts) demonstrates semantic theme tokens, opaque surface, border, radius, slotted content/actions, and optional elevation. It is dated design evidence, not a stable runtime dependency.
- [App security](https://developers.home-assistant.io/docs/apps/security/) recommends least privilege, avoiding host networking, AppArmor, minimal folder/API access, and careful authentication handling.
- [Application Credentials](https://developers.home-assistant.io/docs/core/platform/application_credentials/) provides OAuth2/config-flow helpers for Home Assistant integrations, including local bring-your-own client credentials and PKCE support.
- The official [Spotify integration](https://www.home-assistant.io/integrations/spotify) uses `https://my.home-assistant.io/redirect/oauth`, or `<HOME_ASSISTANT_URL>/auth/external/callback` when My Home Assistant is disabled, and supports multiple account entries.
- A future companion integration can use a config flow and native integration contracts described in the [integration manifest documentation](https://developers.home-assistant.io/docs/creating_integration_manifest/); service/action descriptions and entity platforms remain a separate artifact from the App.

The provider OAuth callback is not solved merely by enabling Ingress. Application Credentials belongs to Home Assistant integrations, not arbitrary Supervisor Apps. Reusing it would require a companion integration or broker with an explicit token-ownership contract. Exact provider redirect URLs, externally reachable Home Assistant URLs, sessions, user-supplied client registrations, and any direct callback listener require a dedicated spike.

Likewise, an Ingress iframe does not automatically provide a stable importable Home Assistant component library. Symphonia's accepted [UI contract](../product/home-assistant-ui-specification.md) treats official components, tokens, and demo/design-portal views as evolving reference evidence; theme/locale/direction/safe-area/base-path context must cross a documented, validated App boundary with deterministic fallback.

## Current conclusion

Spotify is a plausible personal/self-hosted MVP adapter, with meaningful 2026 access and reauthorization constraints. The official YouTube Data API is a plausible **YouTube playlist** adapter, but it is not sufficient evidence for the proposed full **YouTube Music** provider. That distinction is the highest-risk assumption in the current product scope. Apple Music has a promising official library/create/append surface for future scope, but its Home Assistant-compatible authorization flow and missing documented playlist removal/reorder remain open.
