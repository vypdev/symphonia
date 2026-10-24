# RFC: narrow Home Assistant playback broker protocol

**Status:** proposed design for review; no production implementation permission

**Reviewed:** 2026-09-28

**Decision already accepted:** [ADR 0006](../decisions/0006-narrow-home-assistant-playback-broker.md) places Home Assistant Core playback authority in a companion integration, not in the App or browser. This RFC proposes a transport and security contract; it has not been proven in a disposable Home Assistant installation or accepted as the final protocol.

## Deployment and trust model

Home Assistant Core loads a `symphonia` custom integration using a [config flow](https://developers.home-assistant.io/docs/core/integration/config_flow/) and the normal custom-integration [file layout](https://developers.home-assistant.io/docs/creating_integration_file_structure/). The Symphonia App owns its own music data, Ingress UI and internal broker endpoint. Home Assistant's [App communication documentation](https://developers.home-assistant.io/docs/apps/communication/) describes internal App naming/networking; that network helps discovery but is **not** an authorization boundary. A separate internal listener or route must not become an unauthenticated public management API.

```text
authenticated Ingress admin -> App listening use case -> typed broker port
                                                    <-> private, authenticated channel
HA companion integration -> exact allowed HA media_player -> HA player integration
```

Text equivalent: the browser calls only the App's authenticated use case. The paired integration connects to the App over a dedicated channel, reports selected player observations, and executes a closed set of typed operations against one allowlisted Core entity. Library imports, provider grants, playlist copies and audio streams do not cross this channel.

The primary product currently has one local Symphonia user and an admin-only Ingress management surface. This does **not** prove that an App-side action carries the same Home Assistant or Music Assistant user identity. The protocol therefore treats listener identity and playback-source identity as separate evidence. Until the actual MA caller mapping is proven, private per-user MA browsing/playback is denied or explicitly bound to one configured admin/default account without claiming per-listener attribution.

## Candidate transport, not yet selected

**Preferred candidate for the topology spike:** the HA integration initiates one outbound, versioned WebSocket connection to an App listener address discovered from a configured internal App alias. The App never requests `homeassistant_api: true` or holds `SUPERVISOR_TOKEN`; the integration holds Core authority. The channel needs TLS with explicit App certificate/public-key pinning plus a separately generated integration credential, or an equivalently reviewed encrypted and mutually authenticated construction. App alias/DNS, local networking and Ingress cookies are not authenticators.

Why this direction is preferred: the App can send bounded commands and receive observations over one channel without a general Core token, a public HA endpoint, MQTT dependency, or polling every player from the browser. This is a hypothesis: the HA/App network reachability, certificate provisioning, upgrade behavior, and configuration UX must be demonstrated before selection.

| Alternative | Rejection/remaining condition |
| --- | --- |
| App calls HA REST/WebSocket with `SUPERVISOR_TOKEN` | Broad Core credential contradicts ADR 0006 even if application code allowlists calls. |
| Browser calls a custom HA WebSocket command | Browser token/host-context coupling and direct action authority contradict the App-owned use-case boundary. |
| Custom HA HTTP endpoint polled by App | Requires a separately proven narrow authentication/authorization surface and may expose an endpoint beyond the internal network; not automatically safer than a reverse channel. |
| MQTT/general event bus | Adds another service and still needs pairing, exact-target authorization, command correlation and no-replay semantics. |

## Pairing and lifecycle proposal

1. The App creates its installation identity and channel certificate/key inside its protected persistent state. The admin views a short-lived, single-use pairing challenge and the App certificate fingerprint in Ingress. The challenge is **not** the long-term broker credential. No Core, broker or provider bearer token is returned to ordinary browser state.
2. The HA integration config flow asks for the App alias/address and pairing challenge. Before any secret exchange, the admin compares the displayed certificate fingerprint with the one observed by the integration; a mismatch aborts. A successful flow exchanges a new random long-term channel credential over the pinned encrypted channel. The HA-side credential location, export/backup exposure and revocation behavior require proof; a config entry must **not** be presumed encrypted. The App needs an approved protected secret store. Actual certificate/key generation, encrypted key source and backup behavior are release blockers; a self-signed certificate without pin verification is not accepted.
3. A connection starts with mutual challenge/response, installation identities, a fresh session nonce, and major/minor protocol negotiation. An incompatible major version disables listening with a repair message; library/copy remain available. A reconnect gets a new epoch and never drains old commands.
4. An administrator can revoke and re-pair. Rotation overlaps old/new credentials only for one bounded window, fences old sessions, and emits a sanitized audit category. Backup restoration to another HA instance cannot silently reuse the old pairing; the secret/key restore policy must explicitly decide whether to re-pair.
5. On unload/uninstall, the integration cancels subscriptions and closes the channel. The App invalidates observations and pending commands on disconnect; it never queues control actions for replay.

The one-time challenge, certificate fingerprint, long-term secret and Ingress admin identity each have different roles. No authentication material is embedded in an App option, URL, log, diagnostic bundle, artwork URL, playlist reference or copied browser state. Secret storage is blocked by the App runtime SDD's encryption-key/backup decision.

## Minimal version-1 semantic contract

The wire format is not accepted until the topology/threat spike, but every operation must map to a semantic port. Proposed message families:

| Message | Direction | Required checks |
| --- | --- | --- |
| `hello` / `health` | both | installation identity, protocol version, paired channel, feature set; no account names/secrets |
| `players.list` | integration → App | only explicitly allowed `media_player` entities; stable entity ID plus integration/source evidence, never name as authority |
| `player.observe` | integration → App | exact entity, session epoch + monotonic sequence, observation time, bounded safe attributes and effective features; absence stays unknown |
| `media.browse` / `media.search` | App → integration | exact entity, source profile, validated typed cursor/query and current feature/permission check; bounded result page; no raw URL/path |
| `player.command` | App → integration | one exact allowed entity, closed action/media-kind enum, typed exact reference, current feature and account checks, correlation ID, no wildcard/area/broadcast |
| `command.accepted` / `command.rejected` | integration → App | transport/HA dispatch category only; never asserts playback effect |

The action set is initially restricted to read/browse/search where proven and the applicable play, pause, resume, stop, next, previous, seek, volume, source/output and exact-media-start operations. Each is separately feature-gated; the broker may reject an advertised HA feature when the concrete profile is unsafe. MA's permissive name/URL/path search fallback is not an exact media reference. Spotify's name-based source selection is not a stable output ID. A directly consented Spotify Connect adapter, if later approved, uses a **separate** provider port and grant; it does not extend this HA broker's Core authority.

One unresolved command per selected player is allowed from Symphonia. The broker validates operation, entity, profile and reference independently from App-side checks. A successful command dispatch becomes `accepted`; the App confirms `playing`, `paused` or another effect only after a fresh observation matches the requested media/output. A timeout, disconnect or race is `uncertain`; no automatic command retry occurs. Broker session epoch and observation sequence fence stale events; command correlation cannot turn a delayed response into success. External HA controllers may change the same player at any time.

The topology spike must select concrete JSON schemas, maximum request/result sizes, browse pagination, nonce lifetime/replay cache, per-player rate limit, freshness and confirmation budgets. They are **not** left to caller-provided values. Source-specific versioned fixtures must prove every field and rejection path.

## Threat review and negative contracts

| Threat | Required proof |
| --- | --- |
| Another App on the internal network connects or impersonates the broker | Correctly pinned encrypted channel, independent broker credential, pairing expiry/single use, failed-auth rate limit |
| Ingress client forges entity, action, media ID or prior selection | App authorization plus broker-side exact entity/action/media-kind allowlists and stale-selector fence |
| Stolen or restored pairing secret replays an old command | Rotation/revocation, session nonce/epoch, no queued replay, bounded replay defense |
| HA/MA current user differs from Symphonia listener | Distinct caller/source identities; private content denied absent proved binding; no name-only inference |
| Hostile metadata, artwork or diagnostics leak secrets/track history | Bounded sanitized DTOs, safe URL schemes, no raw HA state or listening history in ordinary logs/backups |
| Version skew or broker outage harms library/copy | Playback-only unavailable state and explicit repair path; durable music workflows remain independent |

Every negative contract must have deterministic fake-broker tests and an opt-in disposable-HA test. Security review must include whether internal-network peers can observe/manipulate transport, HA custom integration permission semantics, denial of service from rapid browse/command calls, compromised admin session, upgrade/rollback, and restore-to-new-instance behavior.

## Decision gate

This RFC is ready for a topology/security spike, **not** for production implementation. Select the transport only after a disposable HA installation proves internal alias reachability, config-flow pairing, certificate pinning and storage, mutually authenticated reconnect, exact entity/action enforcement, version skew, admin/MA attribution, and secret-safe backup/restore. Record the selected protocol in a new accepted ADR or an explicit ADR 0006 successor, then update the listening/App-runtime SDDs, catalog and conformance tests together. An unverified design sketch does not clear `OQ-011` or `RG-007`.
