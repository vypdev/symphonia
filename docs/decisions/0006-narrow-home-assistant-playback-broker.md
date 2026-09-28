# ADR 0006: Use a narrow Home Assistant companion broker for playback

- **Status:** accepted
- **Date:** 2026-09-28
- **Scope:** Home Assistant playback observation and control; not provider OAuth or the independent music core

## Context

The owner wants listening and playback controls inside Symphonia's Home Assistant App. [ADR 0003](0003-home-assistant-app-primary.md) makes the App the owner of durable music data and Ingress UI while leaving a companion integration possible. The [playback source review](../providers/playback-integration-source-review.md) shows that HA's Spotify and Music Assistant entities have integration-specific feature, identity, output, queue, and caller-context limits.

The Supervisor Core API proxy would let the App call Home Assistant, but `homeassistant_api: true` plus a server-side Supervisor token is broader authority than a music feature needs. App-side allowlisting would reduce accidental use but would not narrow that credential's underlying Core permissions. A broker can expose only typed playback operations and keep Core access inside an HA custom integration.

## Decision

For Home Assistant playback, build a **narrow companion custom integration** as the broker between the Symphonia App and explicitly allowed existing `media_player` entities. The App remains the product/UI, provider-authorization, library/copy, and listening-policy owner. The broker owns HA entity discovery/observation and dispatch of a small, versioned set of typed media-player operations. It must not own Symphonia's database, provider grants, matching/copy policy, or audio streaming.

The listening feature will **not** enable `homeassistant_api: true` or give the App a general Core API credential as its initial playback path. The browser never receives a Core or broker credential. Only the installed broker may invoke Home Assistant services, and it must enforce an exact entity allowlist, operation/media-kind allowlist, current feature/state checks, and safe caller/account attribution. It may deny a request even when HA advertises a feature.

The broker transport, mutual authentication/pairing, secret rotation/revocation, version negotiation, reconnect behavior, user attribution, state freshness, command correlation, deployment discovery, and failure semantics are **not selected by this ADR**. They are release-blocking contracts in the [listening SDD](../../specs/listening-and-playback-control.md). No generic HA service call, arbitrary entity selector, URL, local path, or title-search request may cross the broker boundary. An accepted broker command is not proof of playback effect.

The companion integration is required **for HA listening**, but remains optional for App-only library/import/copy use. This does not change ADR 0003's decision that provider OAuth belongs to App adapters in the current plan. A later use of HA Application Credentials would need a separate decision.

## Alternatives considered

- **App-to-Core Supervisor proxy:** fewer artifacts but grants broad Core authority to the App. Not selected for listening.
- **Direct Spotify/MA playback APIs in the App:** may solve some device-ID limits but adds separate grants, account/policy obligations, and provider-specific session behavior; not selected as a silent fallback.
- **MQTT/general event bus:** useful for some projections, but introduces another service and does not by itself define authentication, exactly-one target, command reconciliation, or caller attribution.

## Consequences and verification

- App and broker are versioned separately; missing/incompatible broker degrades only listening, not library/copy.
- The broker needs a minimal authenticated local contract and a threat review covering pairing/replay, entity authorization, upgrade/rollback, Ingress isolation, logs, and backup/restore.
- Each supported integration needs a versioned operation matrix. Stock Spotify idle start and exact output are not promised until proven; MA user/queue behavior needs separate proof; unofficial YT Music remains opt-in.
- Contract tests and a disposable Home Assistant installation must demonstrate one-target dispatch, rejected arbitrary Core authority, secret isolation, stale/unknown outcomes, and safe reconnect without replay.
- This ADR chooses the authority boundary only. It does **not** mark the listening SDD `Ready for implementation` or authorize production broker code while its other gates remain open.
