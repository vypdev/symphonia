# RFC: Home Assistant OAuth companion contract

**Status:** proposed protocol, not implemented or approved for production.
**Date:** 2026-10-25. Authority direction: [ADR 0007](../decisions/0007-home-assistant-oauth-companion.md).
Capability contract: [OAuth companion SDD](../../specs/home-assistant-oauth-companion.md).

## Evidence update, 2026-10-30

The separate [native trial](../development/native-oauth-trial-acceptance-2026-10-30.md#corrected-owner-campaign-at-852f3ea)
now proves real Core/My consent, staged-only return, new same-admin confirmation,
private pairing, App-owned grant/restart/refresh and retirement on its declared
owner matrix. PR #35 merged the bounded source; the owner installation and its
dedicated Spotify access were removed. This is not a production protocol or
long-lived recovery/renewal pass. The [readiness review](../development/native-oauth-production-readiness-2026-10-30.md)
maps remaining decisions and production acceptance without changing these bounds.

## Topology and ownership

```mermaid
sequenceDiagram
    actor User
    participant HA as HA native config flow
    participant App as Paired Symphonia App
    participant Spotify
    participant My as My Home Assistant
    User->>HA: Add Symphonia / Connect Spotify
    HA->>App: Prepare bound attempt and PKCE material (private TLS)
    App-->>HA: Prepared attempt, bounded deadline
    HA-->>User: Open Spotify consent
    User->>Spotify: Approve disclosed scopes
    Spotify-->>My: Browser redirect, code and state
    My-->>HA: Browser returns to Core external callback
    HA->>HA: Validate state and stage return; no token exchange
    User->>HA: Confirm linking in authenticated native flow
    HA->>App: Deliver return and completion authorization once
    App->>Spotify: Exchange, verify immutable account and scope
    App->>App: Encrypt grant and activate connection once
    App-->>HA: Safe durable result / connection ID
    HA-->>User: Connected; open Symphonia
```

Text equivalent: the native HA flow prepares an App-owned attempt before
consent. The browser returns through My Home Assistant to Core. An external
callback only stages the result; a fresh authenticated HA confirmation permits
one App exchange and activation. Core never receives the resulting user grant.

| Boundary | Responsibility / retained material |
| --- | --- |
| HA integration adapter | Native config flow, provider redirect adaptation, state/PKCE setup, current admin/flow checks; pending code/verifier only in bounded process memory |
| App authorization application | Attempt ownership, consume-once exchange admission, account/scope validation, connection activation and disconnect fencing |
| App provider/secret adapters | Fixed provider TLS endpoints, encrypted access/refresh grant, rotation/refresh/revocation and opaque secret references |
| HA config entry | App/pair identity, negotiated versions, public client ID, safe connection references and a protected pairing-key reference; no provider code/verifier/token |
| Browser | Native consent/config-flow navigation; no token handoff, cookie export or access to parent-frame storage |

This intentionally reuses **native navigation and callback machinery**, rather
than its default token-storage behavior. The stock helper creates a token-bearing
config entry and `OAuth2Session` owns its refresh. That default must not run for
this bridge. The candidate adapter uses a per-attempt authorizer plus a custom
config-flow completion step; it stages the callback and lets the App exchange.
No private Core patch, monkey patch or fabricated token response is acceptable.
Supported helper extension points, cancellation cleanup and current-admin checks
must be proven on pinned Core versions before this design is implementable.

## Redirect and credential profiles

- Default: register exactly `https://my.home-assistant.io/redirect/oauth` in the
  dedicated BYO Spotify application. The browser must be able to return to the
  selected HA instance. My Home Assistant is a browser redirect service, not a
  tunnel to the App; it is still an external HTTPS hop in the OAuth route.
- Explicit alternative: with My disabled, register exactly
  `https://<browser-reachable-ha-host>/auth/external/callback`. Use existing
  trusted HA HTTPS, including an already configured remote URL, without a new
  App port or proxy. The exact base used at initiation is snapshotted.
- Spotify allows HTTP only for literal loopback redirects. Do not copy the
  HA page's historical LAN-HTTP fallback examples into the Spotify profile.
  Local HA/browser private-network and HTTP-return behavior need their own
  proof; no bypass of browser TLS/security warnings is permitted.
- Initial feasibility profile: `spotify.profile.readonly.v1`, exact scope
  `user-read-private`, PKCE S256, public Client ID only. Client Secret input is
  not part of this profile. The helper/HA credential UX must support that
  truthfully; never ask for a dummy secret to satisfy a generic form.
- Library/copy scopes are a separate versioned profile pending `RG-001`.
  Playback scopes and other providers are not inherited from this proof.
  An adapter requiring a confidential client needs its own secret input,
  encrypted storage and exchange contract before being enabled.
- No credential import from HA Spotify, SpotifyPlus or Music Assistant. The
  same provider account may have independent grants; names do not prove identity.

## Pairing and private channel proposal

Version 1 proposes bounded HTTPS request/response JSON: Core sends
`POST /internal/ha-oauth/v1` over mutually authenticated TLS to a configured
Supervisor-internal App alias, proposed fixed port **8098**. Other methods/routes
are denied; there is no WebSocket, inbound Core endpoint or unsolicited push
in this profile. Core polls safe status only while a flow is pending. There is no host
port mapping, public ingress to this route, HA Core proxy token, `host_network`,
host/config mount or Docker/SSH access. Internal DNS/network proximity does not
authenticate either side. The bounded trial has actual Supervisor-internal
TLS/topology proof; this complete production message/lifecycle contract remains
proposed and requires final-package conformance.

1. App Ingress creates a single-use 256-bit pairing challenge valid for five
   minutes and displays its installation ID and TLS public-key fingerprint.
   Only this setup view may display the temporary challenge; it is never a URL,
   log field or long-term credential.
2. The native HA flow validates a current administrator, asks for the internal
   alias/challenge, and requires explicit fingerprint comparison before sending
   the challenge. HA creates a client key locally. The challenge binds that
   public key to the exact App identity and the `oauth` authority profile.
3. Subsequent sessions require mutual TLS (App pin + enrolled client key),
   pair ID/epoch, exact installation identities and protocol negotiation.
   No TOFU after a mismatch, plaintext fallback or automatically trusted DNS.
4. OAuth and playback enroll separately with distinct keys/profile permissions.
   No message, credential or config-entry migration can enable playback by
   merely enabling OAuth. Sharing a future channel requires separate authorization.
5. [ADR 0008](../decisions/0008-install-local-oauth-keys-and-backups.md) selects
   automatic startup with install-local keys under the trusted host identity.
   Core uses a private key file and safe entry reference; its encrypted HA backup
   may retain that identity. The App excludes all its OAuth private keys from
   ordinary backups and encrypts grants separately. Config entries are not
   encrypted keystores. See `SYM-SEC-015` and the [key contract](local-key-custody-rfc.md)
   for permissions, fail-closed startup, disclosure and distinct recovery rules.
   Final packaging/reset/rotation/publication proof remains required; an App
   option or silently generated replacement key is not a workaround.
6. Revoking a pair increments its epoch, closes active sessions and invalidates
   pending attempts. It does not erase already active provider grants implicitly;
   disconnect is a separate explicit App action. After Core restore the operator
   must revoke the old pair on the App and explicitly re-pair; a copied Core
   identity cannot detect its own cloning. Missing App keys block credentials
   until authenticated reset/new consent, preserving non-secret history. No
   discovery-driven automatic credential restoration is permitted.

## Native flow identity, not an inferred Ingress session

### CSR lifecycle candidate and bounded result

The [successor research](../development/oauth-recovery-and-pairing-lab-2026-10-25.md)
now exercises generated P-256/SHA-256 CSRs, server-owned certificate subject/
extensions, a private local issuer and durable challenge consumption before
issuance. Pending issuance is resumed explicitly; status does not mint keys or
certificates. An admitted renewal requires current-key possession: a domain-separated signature
binds the issued-certificate digest, replacement CSR digest and epoch in the
research fixture, in addition to actual mTLS. The exact certificate must exist
in the issuer ledger; its public metadata cannot admit renewal. Renewal is
fenced by the previous serial and epoch;
only the committed certificate is active. Revoking a pair invalidates its
epoch independently of a still-valid TLS certificate.

The candidate uses a five-minute challenge and ten-minute synthetic client
certificate. The latter is a research lifetime, not a ratified production
renewal schedule. Three real process-death points and newly issued client TLS
pass on the pinned image. A separate [actual-wire campaign](../development/oauth-recovery-and-pairing-lab-2026-10-25.md#actual-coresupervisor-csr-and-ingress-reset)
now proves generated CSR enrollment and renewal, previous-certificate rejection,
key-loss handling and fresh native reset/resume admission through real Supervisor
Ingress. The Core key-file adapter, concurrent renewal/revocation deployment races,
recovery authority/UX review and supported package/browser matrix still need
conformance. HTTP clients manually supply cookies; this is not Chrome proof. No bootstrap or renewal route
is exposed in the production App by these tools.

### Native flow and actor contract

Proposed entry layout: one `symphonia` pair config entry per App installation,
holding safe connection references. The initial native flow pairs and creates
that entry. Provider connect/reconnect then runs as a **main config flow** for
that entry (`reconfigure`/`reauth`), not an options/subentry flow: the inspected
Core external callback dispatches to `hass.config_entries.flow`. Completion
updates safe references only. The supported reconfigure/reauth hook and cleanup
of an entry removed mid-flow must be demonstrated; changing a callback manager
inside Core is not allowed.

The proposed entry point is **Settings → Devices & services → Symphonia**.
An App Connect action links to native setup using documented HA navigation;
it passes no OAuth secret, App cookie or arbitrary return URL. The App UI does
not read HA frontend tokens, parent storage or private frontend modules.

For the public-client proof, a native Symphonia form stores only the public
Client ID/profile and creates a per-attempt PKCE authorizer. It does not reuse
another integration's Application Credentials entry. If the selected supported
HA credential API requires a Client Secret, that generic dialog is unsuitable
for this public-client profile; prove the custom public-ID flow instead of
inserting dummy credentials. Confidential-client profiles remain disabled.

The trusted integration captures the initiator from a current server-validated
HA administrator request, never from form fields or the mere possession of a
flow ID. It creates a server-side binding of actor, HA instance, pair/epoch,
native flow ID, App attempt ID, provider/profile, public client ID, exact
redirect and deadline. Completion requires a **new authenticated native-HA
confirmation by the same admin**, with active user/admin checks, then a
channel-bound one-use completion authorization. The public callback cannot
create that authorization or trigger exchange by itself.

The exact supported config-flow/request hook for proving the current actor at
both steps is a release blocker. Standard Core OAuth state validation binds a
flow; it does not alone prove the initiating browser or active login. If the
supported native flow cannot furnish fresh actor context without private
frontend access, stop and revise this RFC; do not substitute a submitted user ID.

This changes the trial's authority boundary deliberately: **native HA flow +
fresh same-admin confirmation + paired installation** replaces the trial's
original App-browser/Ingress-cookie completion requirement. The App need not
be open in that browser. It must not claim exact Core login-session continuity,
same-browser binding or immediate global logout propagation from this design.
Fresh requests after user disable/logout must fail; a commit already admitted
may finish once. Stronger same-browser or mid-flight revocation semantics need
separate evidence before they can be advertised.

## Version 1 semantic messages and bounds

All proposed envelopes carry protocol major/minor, pair ID/epoch, random message
ID, App installation ID and bounded typed payload. The receiver derives peer
identity from the authenticated channel. Browser fields cannot select the peer.
Unknown operations, keys, scope profiles, duplicate fields and wrong directions
are rejected. No endpoint accepts arbitrary URLs, headers, entity IDs or files.

| Operation | Direction | Effect / idempotency |
| --- | --- | --- |
| `hello` | both | Versions, OAuth profile support and fresh channel epoch; no secrets/account data |
| `attempt.prepare` | Core → App | Bound native flow/actor/profile/redirect, verifier and nonce; persist non-secret attempt metadata, keep verifier only in volatile bounded state |
| `attempt.stage_return` | Core → App | One validated callback result for that binding, either code or denial; no exchange and no reusable receipt authority |
| `attempt.complete` | Core → App | Fresh same-admin native confirmation, staged digest and binding; atomic consume-once admission before provider I/O |
| `attempt.status` | Core → App | Query a previously admitted result over the paired channel; cannot resend code or repeat exchange |
| `attempt.cancel` | Core → App | Invalidate pending attempt, erase transient references; an admitted exchange may need uncertain-result reconciliation |
| `connection.status` | App → Core | Safe ID/result/required action only; not provider grants, playlist content or Core attributes |

Proposed fixed limits, to be verified rather than caller-configurable:

| Bound | Value |
| --- | --- |
| Pair challenge | 256 random bits, single use, 300 seconds |
| Active OAuth attempts | 1 per paired App installation for the initial profile |
| OAuth attempt lifetime | 600 seconds from prepare, never extended by polling |
| Staged return / completion authorization | Within original deadline; code at most 120 seconds in memory; completion authorization 30 seconds, one use |
| Envelope / authorization code | 16 KiB decoded envelope / 8 KiB code |
| PKCE | S256; independent verifier per attempt, 43–128 characters |
| Provider requests | Fixed endpoints, no automatic redirects, 10-second deadline each, 64 KiB JSON body maximum |
| Setup admission | At most 5 pairing failures/minute and 5 OAuth begins/15 minutes per pair/actor, bounded counters |
| Connect / status | 10-second channel connect deadline; status polling at most once/2 seconds, only while pending |

Field-specific schemas, certificate lifecycle, complete error enum and tested
runtime/version matrix must be ratified in the topology/security spike. The
target is a validated single-label App service alias, with a fixed port/path,
not an arbitrary URL, IP/port scanner or caller-selected redirect. TLS pinning
precedes any pairing secret; DNS changes cannot silently establish trust.

## Single owner, crash safety and token lifecycle

Only the App exchanges the staged code. Before I/O it atomically changes the
bound attempt to `exchanging`; a replay, concurrent completion, re-pair or
disconnect cannot acquire a second exchange owner. A denial never exchanges.
After success it verifies scope and immutable account, seals the grant, and
publishes one connection/secret reference. Cross-store publication uses a
recoverable staged-secret record and fenced activation, not two assumed-atomic
writes. Unreferenced sealed records expire and are collected by recovery.

The future persistence migration adds an explicit `ha_native_flow` authority
kind and its immutable HA/pair/flow binding alongside the provider-neutral
attempt. It must not overload an old browser-nonce/session column to claim
Core identity. Existing pending direct-callback attempts expire on profile
migration; non-secret connection history is preserved and no old native/trial
grant is imported. Exact schema/transaction changes are not implemented here.

If an acknowledgement is lost, query the durable attempt result; never resend
the code or repeat exchange. A crash after admission with no proven result
becomes `outcome_unknown`, with no automatic exchange replay. Restart discards
all pending codes/verifiers and requires fresh consent. An existing active
connection remains usable until a replacement grant is verified and committed;
a reconnect to another account is rejected rather than relabeling the old one.

The App is the sole refresh owner and performs versioned single-flight refresh.
Core must not create a provider-token-bearing config entry or `OAuth2Session`.
Consequently it does not independently discover token expiry or refresh the
grant. The App's `action_required` view links to native reconfigure/reauth for
the selected safe connection ID. Outside an active flow, HA performs only
explicit view/setup/lifecycle status reads; no background provider polling or
unsolicited bridge push is part of v1. HA shows the last verified result/time,
not a continuously certified provider-health state; current health lives in
the App. A native repair may be raised from a fresh App status result, never
from stale cached status or a generic connectivity error.
Disconnect fences jobs and refresh, erases App grant material and reports
provider revocation separately. A Spotify revocation endpoint is not assumed;
account-UI revocation may remain required. Removing the auxiliary integration
revokes the pair/pending attempts when reachable; offline removal is reported
as unpair-pending until the App operator revokes it. It is not a promise that
an unreachable App's provider grant has disappeared.

## Review gates and rollout

No production component from this design is installed. The separately authorized
[laboratory validation](../development/ha-oauth-companion-lab-2026-10-25.md)
proves bounded native HTTP, internal TLS and backup mechanisms. Its temporary
Supervisor App was removed afterwards. Existing owner-instance research
trial/tunnel is historical research. The later native owner campaign is
recorded above and removed; no trial or native Spotify configuration/grant is
a production migration source.

Native current-request actor and main reconfigure/reauth hooks now have real
framework HTTP evidence. Pre-issued PKI tests show the private route can reject
wrong pins, clients, profiles and epochs; they do not prove production enrollment
or renewal. Actual App backup exclusion and a locked restore work. However,
private Core files remain plaintext. The owner subsequently selected the
trusted-host automatic-start profile in ADR 0008; [follow-up research](../development/local-key-custody-lab-2026-10-25.md)
proves persistent local-key mechanics and actual protected Core backups, not
hardware sealing. CSR lifecycle, final key adapter/package, rotation/reset,
production activation/recovery and full live/browser conformance remain gates;
the complete protocol is still proposed.

1. Prove native flow hooks, per-attempt PKCE isolation, no default Core token
   persistence, callback-only staging and fresh same-admin confirmation.
2. Prove internal topology, pinned mutual TLS, pairing keys, rate/size limits,
   profile/version isolation and HA/App backup/restore under `SYM-SEC-015`: no
   provider plaintext or App private key in ordinary archives, while protected
   Core backups may retain the native pairing identity.
3. Prove the ADR 0008 key adapter/package and reset/rotation/publication contract
   under the accepted trust direction; do not treat the bounded fixture as production.
4. After SDD readiness and explicit implementation approval, build the minimum
   profile and run the 16-case live matrix in the SDD using a dedicated app.
5. Later approve library/copy scopes separately. Reauthorize rather than import
   the trial/native integration grants. Rollback disables new authorizations;
   it must never reopen a tunnel or fall back to a direct App callback.
