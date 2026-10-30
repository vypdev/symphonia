# ADR 0007: Use a Home Assistant companion for provider OAuth

- **Status:** accepted authority/deployment direction; protocol proposal remains gated
- **Date:** 2026-10-25
- **Supersedes:** the direct-App OAuth and OAuth-optional companion clauses in
  [ADR 0003](0003-home-assistant-app-primary.md), and the OAuth-optional/library
  setup qualification in [ADR 0006](0006-narrow-home-assistant-playback-broker.md).
  Their App-primary, portable-core and narrow playback-authority decisions stand.

## Context

The owner requested a design for a Symphonia auxiliary integration that handles
OAuth like other HA integrations, without Cloudflare, and explicitly required
updating the SDDs before implementation. The separate disposable callback trial
proved private-context/start admission but did not complete the provider return.
It remains research evidence, not the selected production topology.

The official HA Spotify flow uses My Home Assistant and Core's external OAuth
callback. A Supervisor App does not inherit that config-flow machinery merely
because it has Ingress. A loopback callback instead reaches the browser's
computer; it does not reach an App on another HA host.

## Later evidence, 2026-10-30

The [native owner trial](../development/native-oauth-trial-acceptance-2026-10-30.md#corrected-owner-campaign-at-852f3ea)
subsequently completed the selected Core/My route with private pairing, fresh
same-admin exchange confirmation and App-owned grant/restart/refresh. Its
installation and dedicated provider access were removed. This supports the
accepted authority direction without accepting the full proposed production
protocol. The [readiness review](../development/native-oauth-production-readiness-2026-10-30.md)
records remaining gates; the production SDDs stay Draft.

## Decision

In the Home Assistant profile, require a **thin Symphonia custom integration
for new provider OAuth connections and reauthorization**. It owns the native
setup flow and Core callback adaptation. The default registered redirect is
`https://my.home-assistant.io/redirect/oauth`. A separately validated direct
Core HTTPS callback is an alternative when My Home Assistant is disabled.
Neither profile needs a Cloudflare tunnel or a public App callback listener.

The App remains the primary product, durable connection/secret owner, provider
API and refresh/revocation owner, and library/copy/job owner. The integration
must not read App files or database, borrow an existing Spotify integration's
credentials, or become a generic provider/Core proxy. App domain/application
code remains independent of HA. Standalone OAuth is a separate future profile.

OAuth and playback are independent negotiated authority profiles, even if
eventually delivered in one integration package. Enabling OAuth grants no
player access. Existing verified App grants can continue refreshing and serving
provider jobs while Core/the companion is unavailable; new consent cannot.

The [OAuth companion SDD](../../specs/home-assistant-oauth-companion.md) and
[protocol RFC](../architecture/home-assistant-oauth-companion-rfc.md) propose
code/PKCE handoff over a narrow authenticated channel, App-only grant storage,
fresh native-HA confirmation and one-time exchange. These details need the
stated feasibility/security review; this ADR does not certify that protocol.

## Alternatives and consequences

- Direct App callback: retains standalone symmetry but adds redirect hosting
  and another exposed listener. Rejected as the default HA OAuth path.
- Callback on the browser's `127.0.0.1`: useful for a desktop proof, but needs
  a local forwarder/helper to reach the HA App. Not the normal setup path.
- Read/reuse HA Spotify's stored tokens: couples unrelated integrations,
  scopes and refresh owners. Rejected.
- Keep grants in Core and proxy provider operations: avoids handoff but moves
  provider adapters/jobs into a second authority boundary. Not selected here.
- Two artifacts and a private pairing/version contract are real costs. They
  must be visible in setup, support, backup and uninstall guidance.

## Gates

Only the authority direction is accepted. The new companion SDD, authorization
SDD and runtime SDD remain **Draft**. Native actor/flow proof, private-channel
pairing, secret/key/backup policy, provider scopes and local/remote browser
evidence remain production gates despite the bounded trial proof above. The
original request approved design work. Later explicit trial and continuation
authorizations are separate; they do not themselves establish SDD readiness
or production release conformance.
