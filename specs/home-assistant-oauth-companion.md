# Home Assistant OAuth companion

- Status: Draft
- Date: 2026-10-30
- Last verified: Not applicable; this is not an as-built baseline. See the catalog migration audit for source/path verification.
- Catalog capability ID: `home-assistant-oauth-companion`
- Owners: Symphonia maintainers
- Scope: pair a thin HA integration with the App, run native provider consent without a public App callback, and admit one App-owned grant exchange through a verified native flow.
- Related requirements: `SYM-ACC-002`, `SYM-ACC-004`–`SYM-ACC-006`, `SYM-HA-002`, `SYM-HA-004`–`SYM-HA-007`, `SYM-HA-012`, `SYM-SEC-001`–`SYM-SEC-008`, `SYM-SEC-010`, `SYM-SEC-012`–`SYM-SEC-015`, `SYM-PROV-009`, `SYM-PROV-012`, `SYM-PROV-013`, `SYM-PROV-022`
- Related decisions/research: [ADR 0007](../docs/decisions/0007-home-assistant-oauth-companion.md), [protocol RFC](../docs/architecture/home-assistant-oauth-companion-rfc.md), [official research](../docs/providers/provider-research.md#2026-10-25--native-home-assistant-oauth-companion), [ecosystem evidence](../docs/providers/home-assistant-ecosystem-review.md#2026-10-25--oauth-companion-evidence), [authorization](provider-connections-and-authorization.md), [runtime](home-assistant-app-runtime-and-ingress.md), [UI foundation](home-assistant-native-ui.md), `OQ-004`, `RG-002`, `RG-008`
- Related follow-up: [production readiness review](../docs/development/native-oauth-production-readiness-2026-10-30.md), [issue #38](https://github.com/vypdev/symphonia/issues/38)
- Required review gates: product UX, architecture, HA platform, provider feasibility, testing, documentation, security/operations
- Open decisions blocking readiness: supported-version/browser/package conformance of the native hooks; production enrollment/certificate lifecycle and durable pairing; final local-key adapter/package, reset/rotation and backup/restore conformance under accepted ADR 0008; App secret publication/recovery; production PKCE-only credential UX and exact provider scopes; full live conformance. Bounded HTTP/TLS/backup evidence is now recorded below.

## 1. Executive summary

The HA administrator connects Spotify through a native **Symphonia** integration
flow. The registered redirect is My Home Assistant; Core receives and validates
the return. A fresh native confirmation permits the paired App to exchange once,
verify the account and store the grant securely. No Cloudflare, desktop helper,
dynamic Ingress redirect or public App callback is part of this profile.

```text
Install/pair auxiliary integration -> review provider/client/scope -> consent
-> Core stages callback -> same admin confirms -> App exchanges and verifies
-> App activates connection -> existing App adapters refresh/use its grant
```

This is a design contract, not an installed or implemented capability. The
authority direction is accepted; the RFC's transport and concrete hooks remain
proposed. All readiness blockers must close before production implementation.

## 2. Problem, current behavior, and evidence

### 2.1 Problem

Self-hosters should not need a callback tunnel/domain solely to authorize an
App through HA. A direct App callback duplicates machinery already available
to native integrations and adds registration and exposed-listener complexity.

### 2.2 Current behavior

The primary production runtime has no OAuth integration/endpoints. The earlier
direct-callback trial proved private session/start admission, not a real App
grant. A later separate native App/helper completed real owner OAuth, restart,
refresh/account match and owned retirement at `852f3ea`; see section 2.5. It is
not the production adapter. The native Spotify integration remains independent
and is never a credential source. Existing foundation persistence remains
reusable policy evidence rather than this complete capability.

### 2.3 Evidence and unknowns

- Official HA/Spotify facts are dated in [provider research](../docs/providers/provider-research.md#2026-10-25--native-home-assistant-oauth-companion).
- Community SpotifyPlus source evidence is [separate](../docs/providers/home-assistant-ecosystem-review.md#2026-10-25--oauth-companion-evidence); it is not a dependency or provider guarantee.
- The HA helper's default token-bearing config entry is unsuitable for the
  proposed App-only grant owner. A custom supported completion step needs proof.
- No current claim of exact Core login-session, same-browser or immediate
  logout propagation is made. Native flow, current actor and installation
  binding are named separately from the old trial's Ingress/App cookie binding.

### 2.4 Laboratory validation, 2026-10-25

The owner authorized non-production experiments. The
[dated laboratory results](../docs/development/ha-oauth-companion-lab-2026-10-25.md)
separate real framework HTTP, actual Core-to-Supervisor-App TLS, native backup
archives and synthetic crypto records. The [fixtures](../tools/ha_oauth_companion_lab/README.md)
are outside production packaging; their App metadata cannot be discovered by
an ordinary repository scan.

| Area | Bounded result | Remaining gate |
| --- | --- | --- |
| Native hooks | Main reconfigure/reauth, fresh actor, per-attempt S256, staged callback and saved-file canaries pass in isolated Core 2026.9.4 and 2026.10.3 | Supported package/deployment/browser matrix and production adapter conformance |
| Internal pairing/TLS | Actual alias, SPKI pin, client-certificate enrollment/replay/epoch/profile rejection pass with no host port | Pre-issued test PKI does not prove CSR issuance, protected persistence, renewal or durable enrollment |
| Private HA storage | `Store(private=True)` is 0600 but plaintext; follow-up private key reopens and signs in a new process | Accepted trusted-host file profile in ADR 0008; final integration adapter/lifecycle still needs proof |
| Native backups | Password protection rejects wrong key; App exclusion/locked restore pass; follow-up protected Core archive recovers its synthetic pairing key | Encrypted Core archives may retain native identity; final App reset/rotation and full restore conformance remain open |
| AEAD fixture | External-key recovery succeeds; wrong key/domain or tampering fails | Does not select a production encryption/key-management stack |

No provider exchange, real Spotify consent, personal HA changes, public callback
or production implementation occurred. All partial live-case claims are scoped
in the report. This evidence narrows `RG-008`; it does not close it or the 80-case
production budget.

### 2.5 Native owner trial and production gap, 2026-10-30

The [corrected native campaign](../docs/development/native-oauth-trial-acceptance-2026-10-30.md#corrected-owner-campaign-at-852f3ea)
passed on Core 2026.10.4, Supervisor 2026.10.5, HAOS 18.3 and Green/aarch64 in
Chrome: private native pairing, explicit public-client read consent, Core/My
staging, new same-admin confirmation, App-only encrypted grant, App restart,
confirmed refresh/account match and local plus separate provider retirement.
The App/helper/keys/staging/store were removed; both Core restarts completed.
PR #35 merged this bounded implementation into develop at `9601681`.

Its 54 source/package cases and real owner run establish the selected route's
bounded feasibility. They do not execute this SDD's 80 production cases or 16
live production cases. Long-lived enrollment/renewal, key recovery/rotation,
concurrent connection publication and supported artifact/browser conformance
remain open. The [manual readiness review](../docs/development/native-oauth-production-readiness-2026-10-30.md)
maps every L-case to relevant observations and the remaining work. This SDD
stays Draft; no trial grant, key or config entry migrates to production.

## 3. Actors, surfaces, and terminology

| Actor | Goal | Entry point | Visible surfaces |
| --- | --- | --- | --- |
| HA administrator | Pair, authorize, reconnect, unpair | Settings → Devices & services → Symphonia | Native config flow and repair/status text |
| Provider account holder | Approve or deny disclosed access | Spotify consent | Provider-owned browser page |
| App operator | Inspect connection, disconnect and recover | Admin-only Ingress | Shared connection/status components |
| Companion adapter | Validate native flow and deliver bounded return | Authenticated HA request + private paired channel | Safe config-entry result only |

**Pair** binds one HA integration identity to one App installation and authority
profile. **Native flow** is the short-lived HA config-flow transaction.
**Staged return** is a code/denial awaiting authenticated confirmation, not a
grant. **Active grant** exists only behind the App secret-store reference.

## 4. Goals, non-goals, and fixed invariants

### 4.1 Goals

1. Provide normal HA setup/reauthentication without a public App callback.
2. Keep provider grants and background refresh usable in the App independently
   of Core after successful connection.
3. Bound actor, installation, redirect, provider/profile, attempt and expiry;
   make every failure/recovery state visible without exposing secrets.

### 4.2 Non-goals

Audio/player control, library import/write policy, a generic Core/provider proxy,
shared hosted Spotify registrations, standalone OAuth and unofficial provider
authentication are not applicable to this vertical. It grants no playback
authority and imports no existing integration's credential or config entry.

### 4.3 Fixed invariants

1. Only fresh native-HA admin actions can authorize completion; a public callback
   or possession of a flow ID cannot. Same actor as initiation is required.
2. Channel identity and a server-held flow binding select the App/attempt;
   submitted IDs, names, headers and network location cannot grant authority.
3. Only the App exchanges, activates, refreshes and revokes the provider grant.
   Core stores no provider code, verifier or grant durably.
4. Public callback data is staged, bounded and single-use. Exchange admission
   is fenced before I/O; unknown outcomes are not blindly repeated.
5. Ingress remains the App's UI management boundary. The independent OAuth
   channel permits only its typed bridge operations, never UI/API management.

<a id="5-product-journey"></a>

## 5. Current versus proposed product journey

| Stage | Proposed behavior | User/operator effect |
| --- | --- | --- |
| Pair | View setup challenge/fingerprint in App; enroll from native HA flow | One installation, explicit OAuth-only permission |
| Configure | Enter dedicated public Client ID and fixed redirect/profile | No Client Secret/dummy field for PKCE-only Spotify |
| Review | Name provider, exact functional access, grant owner and dependencies | Consent before leaving HA |
| Authorize | Prepare bound attempt, open Spotify, stage Core callback | No exchange just because a URL was opened |
| Confirm | Same admin submits fresh native confirmation | One App verification/activation, bounded spinner |
| Complete | Show verified account/capabilities and open App | Import remains a separate operation |
| Reconnect/remove | New consent or explicit unpair/disconnect | Existing data and external revocation status are explained |

The [sequence diagram and text equivalent](../docs/architecture/home-assistant-oauth-companion-rfc.md#topology-and-ownership)
define the dependent browser, Core and App transitions.

## 6. Functional behavior and state model

### 6.1 Happy path

1. Install the independently versioned integration only after an approved
   artifact exists. Native pairing enrolls the App identity and `oauth` profile.
   One HA config entry represents the pair. Provider connect/reconnect uses a
   main reconfigure/reauth config flow, not options/subentries, so Core's native
   callback manager resumes the correct kind of flow. The trial proves its main
   reconfigure path; the production reconfigure/reauth adapter still needs its
   own conformance evidence.
2. Start in HA settings; an App Connect action is a documented navigation link,
   not an HA API client or a secret-bearing URL.
3. Capture a server-validated administrator and per-attempt authorizer. Prepare
   the App attempt with actor, flow, pair/epoch, provider/profile, client ID,
   exact redirect, PKCE and a 600-second deadline before opening consent.
4. Core validates its returned OAuth state. The integration stages code/denial
   against that exact binding. No token exchange occurs in Core or the callback.
5. A new authenticated same-admin native confirmation supplies one-use completion
   authorization over the private channel. Reject absent/unprovable actor context.
6. The App consumes once, exchanges using fixed endpoints, verifies exact granted
   scope and immutable identity, and publishes the encrypted grant/reference.
7. HA receives safe status/ID only. App provider operations and single-flight
   refresh no longer depend on the companion's availability.

### 6.2 Alternative and boundary paths

- Denial/expiry/cancel clears transient material without a connection.
- Reauthentication preserves the old active connection until verified replacement;
  a different immutable account requires explicit independent setup.
- A second browser has no inherited authority from a flow ID. The design allows
  a fresh same-admin native confirmation, without claiming original-browser
  continuity; another admin/disabled user cannot take over the pending flow.
- A Core/App restart abandons transient callbacks/PKCE. An already admitted
  exchange is queried by durable result; unknown results require fresh consent.
- Incompatibility, unpaired state or unavailable Core blocks **new consent**.
  It does not revoke an existing App grant or enable direct-callback fallback.

### 6.3 State machine

| State | Entered when | User-visible meaning | Allowed next states | Recovery/owner |
| --- | --- | --- | --- | --- |
| `unpaired` | no valid OAuth pairing | Auxiliary setup required | `paired`, `blocked` | admin compares/enrolls |
| `paired` | versions/profile and keys valid | Ready to configure provider | `prepared`, `unpaired`, `blocked` | admin starts consent |
| `prepared` | App accepted full bound attempt | Waiting for provider | `return_staged`, `denied`, `expired`, `cancelled` | provider/user |
| `return_staged` | validated callback staged once | Confirm link in HA | `exchanging`, `expired`, `cancelled` | same admin, fresh request |
| `exchanging` | one durable owner admitted | Verifying account | `connected`, `failed`, `outcome_unknown` | App only |
| `connected` | encrypted grant/reference activated | Named capabilities ready | reconnect/new attempt, disconnected | App lifecycle |
| `outcome_unknown` | exchange/activation result unproven | No success claim or replay | proven result, new consent | status/recovery |
| `blocked` | mismatch or unsafe setup | New authorizations unavailable | `paired`, `unpaired` | explicit repair |

Denied/expired/cancelled/failed attempts are terminal tombstones. Duplicate or
out-of-order callbacks cannot replace a staged return or create another owner.

<a id="7-configuration-contract"></a>

## 7. User-facing configuration

All names/limits below are proposed, not shipped options. Validate before
creating a flow; configuration cannot weaken identity, TLS, scope or expiry.

| Input | Type | Recommended default | Allowed values/range | Scope/persistence |
| --- | --- | --- | --- | --- |
| Authority profile | enum | `oauth` only | separately approved profile | pair enrollment; separate from playback |
| App target | internal alias + fixed port | operator-selected known App alias, proposed 8098 | bounded internal App target, no arbitrary URL/path | HA safe config |
| Server pin | SHA-256 public-key fingerprint | no implicit trust | exact operator-confirmed pin | HA safe config |
| Pair challenge | transient secret | absent outside pairing | 256 bits, 300 seconds, one use | setup-only, no durable/plaintext export |
| Client ID | public string | dedicated BYO app | provider-validated identifier | safe adapter config |
| Credential profile | enum | `spotify.profile.readonly.v1` for proof | versioned allowlist; library/copy pending | snapshotted attempt |
| Redirect profile | enum | My Home Assistant | fixed My URI or explicit exact trusted Core HTTPS callback | adapter/attempt; no dynamic Ingress URL |

Precedence is accepted deployment profile → validated pairing/config → immutable
attempt snapshot. An option change cancels pending attempts; it cannot rewrite
their scopes, redirect or destination. Provider secrets are never App options.
Key references resolve only through the ADR 0008 private-file adapter. Core
pairing keys are deliberately local plaintext under trusted-host permissions,
with encrypted HA backups; no config-entry/App-option fallback is allowed.
App OAuth private keys are excluded from ordinary backups. Setup discloses the
host and backup trust boundary and requires acknowledgement that HA backups
must be encrypted, without claiming to inspect every existing archive. Standalone
configuration is not applicable and remains separately gated.

## 8. Clean Architecture design

### 8.1 Responsibilities and dependency direction

| Boundary | Owns | Must not own/import |
| --- | --- | --- |
| Domain/pure policy | Bound attempt, phase, result and identity rules | HA/HTTP/SDK/storage |
| App application | Prepare/stage/complete/cancel/status, activation fences | Core config entries or native framework DTOs |
| HA adapter | Native flow, callback/state adapter, fresh actor proof | App DB, durable provider grants, import/copy/player logic |
| Provider/secret adapters | Exchange/profile/refresh/revoke; sealed storage | HA UI or broad upstream proxy |
| Infrastructure/composition | Paired TLS, protocol/profile checks, lifecycle | Implicit account or actor equivalence |
| Presentation | Native HA forms and App safe status | Token values or duplicated authorization policy |

### 8.2 Contracts, durable state, and trust boundaries

- Ports: native-authorization bridge, attempt/connection repositories, provider
  authorization, secret store, clock, audit and cleanup scheduler.
- HA config: pairing/key reference, public registration and safe connection IDs.
  App durable metadata: immutable binding, phase, consume fence/result, connection
  and secret reference. Codes/verifiers remain bounded volatile material only.
- The [RFC](../docs/architecture/home-assistant-oauth-companion-rfc.md#version-1-semantic-messages-and-bounds)
  enumerates directional operations, payload/TTL/rate bounds and refusal rules.
- Secret publication is recoverable across stores. A lost acknowledgement uses
  status; an uncertain exchange is never retried from the callback.
- Browser/provider data, internal peers, backup files and native callback fields
  are untrusted. Only the paired adapter may attest current HA actor/flow facts.
- Closed error categories distinguish pairing/version/storage, denial/expiry,
  actor/state mismatch, provider outage/invalid grant and uncertain outcome.

### 8.3 Executable architecture constraints

Planned checks reject HA imports from App domain/application, App DB access from
the integration, durable Core tokens/PKCE, default token-bearing config-entry
creation, generic proxy operations, OAuth-to-playback authority escalation,
secret-bearing logs/diagnostics and public App callback/management ports.

## 9. UI/UX and content contract

Native setup uses HA's own config-flow forms and translations. This is an
intentional host-owned surface, not a second App component system. App connection
rows, alerts, buttons and pending/result states inherit the [UI foundation](home-assistant-native-ui.md).
The App never accesses parent DOM/storage to discover a session.

### 9.1 Information hierarchy

Show pairing/connection state, verified facts, next action, impact and retained
data first; collapse safe versions/IDs. Never show query strings or grant data.

### 9.2 Representative states

```text
Pair Symphonia: compare the App fingerprint, then enter its temporary pairing code.
Waiting for Spotify: finish the consent tab. No provider connection exists yet.
Confirm Spotify linking: continue as the administrator who started this setup.
Verifying Spotify: consent returned; Symphonia is checking account and access.
Connection result unknown: check status; do not repeat authorization completion.
Auxiliary integration unavailable: new connections are paused; existing verified App grants remain available.
Spotify connected for profile access: library import and playback are not granted by this test profile.
```

Failure text names cause, next action and retained state; a provider outage
does not demand reauthorization. A denied flow says no connection was created.

### 9.3 Accessibility and localization

Use native form validation/keyboard/focus and English/Spanish translations;
App views inherit locale fallback and live-region rules. Phone/wide and long
labels must retain all actions. Escape/truncate provider display names. External
consent links name their destination; diagrams have text equivalents.

## 10. Failure, recovery, and cleanup

| Failure/partial state | User impact | Retained facts | Automatic retry | Required action | Cleanup |
| --- | --- | --- | --- | --- | --- |
| Wrong pin/pair/version/profile | no new consent | safe config/reason | no downgrade | re-pair/update | pending attempts invalidated |
| Missing/non-admin/different actor | no exchange | audit category | no | initiating admin resumes | expiry clears staged data |
| Wrong/duplicate state or redirect | no connection | terminal reason | no replay | fresh consent | drop code/verifier |
| Core/App restart before exchange | no new connection | non-secret tombstone | no secret recovery | fresh flow | erase transient state |
| Lost completion acknowledgement | pending/unknown result | durable admitted result | status only | wait/inspect result | never second exchange |
| Exchange or activation outcome unknown | no ready claim | fenced attempt/outcome | no blind retry | reconcile/new consent | sealed orphan cleanup |
| Scope/account verification fails | replacement not active | prior connection unchanged | no grant expansion | correct account/profile | delete staged local grant; state external revoke separately |
| Companion removed while App offline | unpair pending | existing App connection/history | bounded reconnect/status only | revoke pair in App | no false provider-disconnect claim |
| App disconnect races with refresh/completion | no new work | disconnect fence/history | none for stale owner | reconnect separately | erase local credentials |

## 11. Security, permissions, and privacy

1. Fresh server-validated HA admin identity is required at initiation/confirmation;
   tests must demonstrate that the supported flow hook provides it. Default
   OAuth state checking does not substitute for this gate.
2. Pair identity, epoch, flow/attempt binding, exact redirect and scope/profile
   remain immutable; mTLS and one-use completion protect the private channel.
3. Core callback is public by the native protocol; it only stages. OAuth codes
   necessarily traverse provider/browser callback URLs, but are never echoed
   into result text, query logs, ordinary state or support evidence.
4. Store grants encrypted only in the App. Enforce `SYM-SEC-015`: private
   Core pairing files may occur in encrypted Core archives; exclude all App
   OAuth private keys from ordinary App backups. Missing/unsafe existing keys
   block credential operations without silent rekey or data deletion. Setup
   discloses host trust and requires encrypted-backup acknowledgement; it does
   not certify historical archives or request backup-inspection privileges.
5. No broad Core credential or playback permission is requested. Admin compromise
   remains a privileged threat; provider/backend permissions are not per-user sandboxes.
6. No claim of Python memory zeroization or continuous Core-session revocation.
   Logging/canary tests include framework debug/error paths and backup artifacts.

## 12. Observability and operational UX

Expose safe pair/profile/version, phase/result and next action. Audit start,
callback category, confirmation, exchange admission/commit, re-pair and disconnect
without URLs, raw headers, codes, keys or tokens. Pending polling is bounded;
stable connected state is quiet. Only required action or meaningful failure
notifies; Core absence and provider outage remain distinct categories.
HA's safe result includes observation time; without a fresh status read it
cannot certify current provider health. App `action_required` links to native
reconfigure/reauth; Core does not need a token or background provider poll to
support that navigation. Pair status is distinct from provider health.

## 13. Compatibility, migration, rollout, and rollback

Separate App/integration releases negotiate protocol major and OAuth profile
before consent. A mismatch disables new consent without weakening TLS or
corrupting active App connections. No native Spotify grant or disposable trial
grant is imported; initial migration is explicit new consent.

A Core backup may copy the complete pairing identity. The operator must revoke
the previous App pair and explicitly re-pair after Core restore; no automatic
clone/restore detection is promised. Revocation fences pending attempts and
closes old sessions. Until revocation a copied private key may remain trusted.
App restoration without excluded keys locks credential operations while retaining
non-secret library/history. Only an authenticated explicit reset may fence old
attempts/refresh/refs, create a new credential identity and require new pairing
and consent; startup/health cannot reset keys. External provider revocation is
a separate outcome. These recovery rules follow ADR 0008.
Downgrade disables this profile rather than exposing a callback tunnel. Schema
and staged-secret recovery need fixtures before release. Non-provider music
data and accepted operation history are retained by their own SDDs.

## 14. Testing strategy and numeric budget

Minimum **80 distinct planned cases**. None is claimed implemented by this design.

| Area | Minimum distinct cases | Behaviors/risks covered |
| --- | ---: | --- |
| Configuration/pure binding policy | 12 | profiles, exact redirect, client/actor/pair/schema validation, fixed bounds |
| State/application/idempotency/races | 20 | staged-only callback, denied/expiry, consume fence, lost ack, disconnect and activation races |
| Native HA/provider/channel adapters | 18 | supported hooks, per-flow PKCE, current admin, pin/mTLS, no default Core token storage |
| HTTP/UI/accessibility/sanitization | 10 | native forms, App links/status, English/Spanish, phone/keyboard, hostile and secret canaries |
| Integration/security/migration | 20 | version/profile separation, restart/restore, key backups, orphan recovery, no public callback or Core proxy |
| **Total** | **80** | No double counting |

These supplement the authorization **82** and runtime **58** case budgets;
reused fixtures do not count as multiple proven requirements. Use fake clocks,
provider transport, native actor contexts and paired channels in ordinary CI.
Existing coverage floor stays 85% combined line/branch. Source-string tests
alone cannot establish native actor or the distinct Core/App backup contract.

Opt-in live evidence requires **16 cases** through the actual bridge, with exact
Core/Supervisor/App/integration/browser versions and dedicated read-only consent:

| Case | Required observation |
| --- | --- |
| L01 | Internal discovery, pin comparison and one-time pairing; no host port |
| L02 | Default My redirect returns from a local browser path to correct Core |
| L03 | Remote browser returns through the declared HTTPS HA path |
| L04 | Supported direct-Core HTTPS alternative works when My is disabled |
| L05 | Current initiating admin + fresh native confirmation activates once |
| L06 | Non-admin/different admin/forged actor or flow ID cannot complete |
| L07 | Logout/user disable before confirmation denies exchange; no broader revocation claim |
| L08 | Missing/wrong/duplicate/expired state and wrong redirect cannot activate |
| L09 | Denial, cancel and expiry erase staged data without exchange |
| L10 | Two authorizers never share PKCE; mismatch cannot exchange |
| L11 | Lost ack, duplicate completion and concurrent disconnect yield at most one owner |
| L12 | Core/App restart abandons volatile secrets; unknown exchange is not replayed |
| L13 | Immutable account, exact scope and App-only single-flight refresh pass |
| L14 | Profile/key/version mismatch and unpair block new consent, without player authority |
| L15 | Backups contain no plaintext provider grant/code/verifier; all App OAuth private keys are excluded; correct decryption may reveal the Core pairing key, wrong password fails; logs/diagnostics expose no credential/key |
| L16 | Disconnect and uninstall show local erasure versus external revocation; native Spotify is unaffected |

Each named case needs its negative subcases. The old direct-callback matrix
and separate loopback success cannot substitute for these bridge observations.

## 15. Documentation and discoverability

| Audience | Artifact | Required content | Validation/navigation |
| --- | --- | --- | --- |
| User/setup owner | [Setup and recovery preview](../docs/operations/home-assistant-oauth.md) | two artifacts, pairing, redirects, public Client ID, normal/reauth flow | native-form and documentation review |
| Operator | Same guide + RFC | unavailable/unknown results, key/backup, remove versus disconnect | failure matrix and live L11–L16 |
| Contributor | RFC + this SDD | extension hooks, semantic ports, authority, strict schemas and tests | architecture/conformance suite |

## 16. Acceptance scenarios

1. Given no companion or incompatible pairing, Connect explains setup; no direct
   App callback/tunnel/Core-token fallback is enabled.
2. Given a validated native admin flow, consent uses the exact selected Core/My
   redirect and disclosed scopes; callback arrival alone cannot exchange.
3. Given fresh same-admin confirmation on the bound flow, the App admits at most
   one exchange, verifies identity/scope and activates one sealed grant reference.
4. Given another actor, forged flow, stale pair/epoch or expired result, no new
   connection or grant refresh is admitted from that request.
5. Given denial/restart/unknown result, the UI states retained facts and next
   action truthfully; unknown outcomes are not replayed as success.
6. Given an existing active grant and Core outage, eligible App work/refresh
   continues while new authorizations are disabled.
7. Given OAuth-only enrollment, playback/general Core operations are rejected;
   no provider grant reaches a HA config entry/entity or browser DTO.
8. Given lost acknowledgement or cross-store activation failure, recovery queries
   the result/collects sealed orphans without repeating code exchange.
9. Given supported language/phone/keyboard fixtures, native forms and shared App
   components preserve all actions and safe focus/status announcements.
10. Given restore/removal/disconnect, pairing and grants follow their distinct
    documented cleanup rules and never silently revive native/trial credentials.

11. Given a valid private key, restart reopens the same identity; wrong owner,
    mode, link/type, size, version or key blocks credential operations without
    rekey, data loss or secret output. Explicit setup discloses trusted-host
    custody and requires encrypted HA backups.
12. Given a protected Core archive, correct decryption may recover the pairing
    identity and a wrong password fails. After Core restore the operator revokes
    the previous App pair and re-pairs; copied identities are not self-detecting.
13. Given App restore without excluded keys, credentials remain locked and
    non-secret library/history survives. Only authenticated explicit reset
    fences old authority and creates new pairing/consent; startup and health
    cannot reset, and no external Spotify revocation is falsely claimed.

The selected local-key profile is defined by [ADR 0008](../docs/decisions/0008-install-local-oauth-keys-and-backups.md)
and the [key contract](../docs/architecture/local-key-custody-rfc.md). Private-file
keys trust the host/service identity; they are not hardware-sealed. Its bounded
[lab evidence](../docs/development/local-key-custody-lab-2026-10-25.md) is separate
from this SDD's unchanged production test budget and release acceptance.

The follow-up also proves eight synthetic file/SQL process-death points and
four additional key/publication fences. This is single-record/quiescent research;
final rotation/lease, collection and authenticated reset admission remain open.


The [recovery/CSR follow-up](../docs/development/oauth-recovery-and-pairing-lab-2026-10-25.md)
adds twenty-one three-record publication/rotation/reset process-death points,
four actual missing/wrong-key cases and twenty-five fake-AEAD policy cases.
Dynamic CSR research passes thirty-six observations including three issuance
process deaths. A separate real-Core HTTP/signature prototype passes thirty-six
observations plus fourteen ordinary binding/resume cases. The guarded
Core 2026.9.4/Supervisor 2026.10.4 wire repeat passes thirty-four Boolean observations:
CSR enrollment/renewal, stale-certificate denial, App-key loss with live Ingress,
fresh native admin approval, actual App Origin/CSRF enforcement and interrupted
reset with a new signed resume. A separate actual child death after reset commit
before pair revocation passes ten observations: startup revokes idempotently
before TLS, serializes renewal/reset and never rearms a consumed challenge.
Thirteen ordinary boundary/operator/renewal cases are
separate. Ingress still returned 200 after user deactivation; native HTTP denied
that user. Manual lab cookies are not browser/HTTPS proof. The signed recovery
authority/UX remains proposed; final package/restore, production concurrency and
browser/provider conformance remain open. No result establishes readiness or
counts toward the unchanged production budgets.

## 17. Requirements traceability

| Requirement | Policy/use case/adapter/presentation | Test or evidence | Documentation |
| --- | --- | --- | --- |
| `SYM-HA-012`, `SYM-SEC-001`, `SYM-SEC-006` | native flow + bound attempt | scenarios 1–4; L02–L10 | setup/RFC |
| `SYM-SEC-012` | fresh actor and completion authorization | scenarios 2–4; L05–L07 | identity contract/RFC |
| `SYM-SEC-013`, `SYM-SEC-007` | one owner, status and refresh fences | scenarios 3, 5, 8; L11–L13 | recovery guide |
| `SYM-SEC-003`–`SYM-SEC-005`, `SYM-SEC-014` | App secret owner, redaction/cleanup | scenarios 7–8, 10; L13–L16 | key/backup and disconnect guide |
| `SYM-SEC-015` | private key/startup/reset and operator restore lifecycle | scenarios 11–13, L15; bounded follow-up evidence, final fault/reset tests pending | ADR 0008, key RFC and recovery guide |
| `SYM-HA-004`–`SYM-HA-007`, `SYM-PROV-009` | isolated adapters/typed channel | scenarios 6–7; L14–L15 | architecture/RFC |
| `SYM-ACC-002`, `SYM-ACC-004`–`SYM-ACC-006`, `SYM-PROV-022` | account/scope/disclosure presentation | scenarios 2–3, 6, 9–10 | user guide |
| `SYM-PROV-012`, `SYM-PROV-013` | deterministic vs opt-in verification | section 14 release matrix | contributor guide |

## 18. Implementation sequence

1. Close `RG-008` native-hook/topology/key/compatibility proof and relevant
   `RG-002`/`RG-001` secret/provider blockers. Accept reviewed protocol details.
2. Verify this SDD is ready and the final scope remains within the owner's
   standing implementation/testing authorization; seek new approval only for
   a material scope or access change. Readiness is not established by consent.
3. Add failing conformance/dependency tests, pure binding states and App ports.
4. Implement protected pairing/native flow and staged-code bridge; App secret
   publication and provider lifecycle remain their owning capability contracts.
5. Add native forms/shared App status, translations, recovery and removal UX.
6. Run deterministic budget and dedicated-account live matrix before a release;
   library/copy profiles remain separately gated until their own proof.

## 19. Definition of Done

- [ ] SDD is `Ready for implementation` and separate owner approval exists.
- [ ] Supported native hooks prove fresh admin identity and callback-only staging.
- [ ] Pairing/keys/version/profile/backup contracts pass `RG-008`.
- [ ] Every requirement maps to acceptance; 80 distinct cases and coverage pass.
- [ ] App exchange/publication/refresh/disconnect recovery is proven.
- [ ] All 16 live cases have dated results/declared supported-profile limits.
- [ ] No Core grant persistence, token DTO, public App callback or authority expansion exists.
- [ ] Native/App UI, localization/accessibility and secret-canary gates pass.
- [ ] Setup, operator, contributor and catalog evidence are current.

## 20. References and decisions

ADRs 0007 and 0008 accept the companion authority and local-key trust directions,
respectively. The RFC and numeric
transport proposal await conformance/security review. ADR 0003's App-primary
and ADR 0006's narrow playback decisions continue under that refinement.
Standalone, confidential-client/other-provider profiles, full library/copy
scopes and additional native entities/actions remain outside this increment.

### Catalog migration audit — 2026-10-29

The catalog now uses the unmodified Copilot SDK v1 inventory contract. `lastVerified` records this source/path audit, not a live acceptance run. The document status above retains design readiness; inventory `proposed` does not authorize implementation. Existing foundation and laboratory paths are evidence of their bounded scope only. The numeric test budget and outstanding product decisions remain in force.

The listed research probes do not constitute a production integration. The separate native trial now has bounded owner OAuth acceptance in section 2.5; it does not complete this production contract.

Requirement inventory retained from the previous catalog:

`SYM-ACC-002`, `SYM-ACC-004`, `SYM-ACC-005`, `SYM-ACC-006`, `SYM-HA-002`, `SYM-HA-004`, `SYM-HA-005`, `SYM-HA-006`, `SYM-HA-007`, `SYM-HA-012`, `SYM-SEC-001`, `SYM-SEC-002`, `SYM-SEC-003`, `SYM-SEC-004`, `SYM-SEC-005`, `SYM-SEC-006`, `SYM-SEC-007`, `SYM-SEC-008`, `SYM-SEC-010`, `SYM-SEC-012`, `SYM-SEC-013`, `SYM-SEC-014`, `SYM-PROV-009`, `SYM-PROV-012`, `SYM-PROV-013`, `SYM-PROV-022`, `SYM-SEC-015`.

Outstanding blockers retained from the previous catalog:

- RG-008 production package/browser/deployment conformance beyond isolated native HTTP proof on Core 2026.9.4 and 2026.10.3
- RG-008 final enrollment/renewal adapter, deployment concurrency and full size/rate conformance beyond actual generated-CSR/Supervisor wire proof
- Final local-key adapter/package, production rotation/publication concurrency, recovery authority/UX and full backup/restore conformance under accepted ADR 0008
- RG-002 App-only provider exchange, secret publication, uncertain-outcome and disconnect recovery
- RG-001 production PKCE-only client UX and exact provider capability/scope profiles
- 80 planned production cases and 16 live bridge cases remain unimplemented/unproven; research fixtures are separate
