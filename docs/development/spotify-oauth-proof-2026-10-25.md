# Spotify OAuth and Home Assistant feasibility proof

**Observed:** 2026-10-25. **Issue:** [#26](https://github.com/vypdev/symphonia/issues/26).
**Status:** research evidence; authorization and App-runtime SDDs remain Draft.

## Baseline and platform results

Master `f780ea378db1b80b67214647583157aee3a5a858` passed
[Verify attempt 2](https://github.com/vypdev/symphonia/actions/runs/40158619579/attempts/2).
All seven jobs succeeded: Python 3.11/3.12/3.13, both UI packages, playback
Compose configuration and 89% combined line/branch coverage against the
unchanged 85% floor. The research branch additionally passes 409 Python tests
with 89% combined line/branch coverage.

The pinned [App lab](ha-app-lab.md) was rebuilt from the integrated App source:
Core `2026.9.4`, Supervisor `2026.10.4`, local App `0.1.0`, aarch64/macOS/OrbStack.
Supervisor is healthy but reports unsupported; this is not production certification.

| Live request | Result |
| --- | --- |
| Ingress without session | HTTP 401 |
| Authenticated health, readiness, root, JS and dashboard | HTTP 200 each; dashboard ready |
| Authenticated App `/oauth/callback` | HTTP 404 |
| Authenticated App `/api/connections` | HTTP 404 |

The original probe's empty session payload returned HTTP 400. The installed
Supervisor `supervisor/api/ingress.py` schema now requires `user_id`. The
corrected probe selects exactly one active owner from the **disposable Core**
user metadata and fails closed on missing, inactive, malformed or ambiguous
ownership. It emits no user ID, session, route token or credential. Six probe
tests include eight distinct owner-selection fixtures and invalid-ID preflight.
This internal diagnostic session does not prove browser authentication or
binding of an OAuth attempt to an initiating Home Assistant administrator.

An owner-provided Home Assistant instance was inspected in Chrome. Its native
Spotify integration showed a configured Premium account without a visible
setup error. No integration, credential or playback state was changed. This
observation is not a fresh OAuth test or a Symphonia connection.

The subsequent [App callback/session preflight](app-oauth-session-preflight-2026-10-25.md)
records the owner's actual Core/Supervisor versions, absent Symphonia App,
missing HTTPS callback route, a separate runnable synthetic session experiment,
and deployment prerequisites. It does not upgrade this local provider proof
to a real Home Assistant actor/session-binding pass.

## Official evidence checked on 2026-10-25

No community implementation establishes the following provider contract.

| Official source | Dated observation and limit |
| --- | --- |
| [Spotify redirects](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri) | Register the exact URI. HTTPS is required except for literal loopback IPs; `localhost` is not accepted. Loopback reaches the browser's computer, not a remote App. |
| [Spotify PKCE](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow) | S256 binds the verifier to authorization-code exchange. The research client requires the Client ID and no Client Secret. |
| [Scopes](https://developer.spotify.com/documentation/web-api/concepts/scopes) and [profile](https://developer.spotify.com/documentation/web-api/reference/get-current-users-profile) | Request only `user-read-private`; verify immutable identity without retaining profile data. Consent includes public profile access. No email, playlist-write or playback scope is requested. |
| [Refresh](https://developer.spotify.com/documentation/web-api/tutorials/refreshing-tokens) | PKCE refresh includes the Client ID; replacement refresh tokens may be omitted. Invalid grants require reauthorization. An immediate refresh does not prove long-term expiry or durable recovery. |
| [Development Mode](https://developer.spotify.com/documentation/web-api/concepts/quota-modes) | The app owner requires Premium and up to five authenticated users must be allowlisted. Consent alone does not prove API access. |
| [HA Spotify](https://www.home-assistant.io/integrations/spotify/) and [My HA](https://www.home-assistant.io/integrations/my/) | `https://my.home-assistant.io/redirect/oauth` relays the native integration flow to Home Assistant. It is not the App-owned Symphonia callback. |

## Reproduce the isolated provider proof

The [research client](../../tools/spotify_oauth_spike.py) lives outside the
production package and App image. Use a dedicated test application/account
and register exactly `http://127.0.0.1:8765/oauth/callback`. On the same computer
as Chrome, run:

```text
PYTHONPATH=src:. python3 tools/spotify_oauth_spike.py --client-id <public-client-id>
```

Open `http://127.0.0.1:8765/`, review the Spotify permission and explicitly
approve consent. The client checks one profile, refreshes once, verifies the
same account again, discards grant references, displays safe result flags and
exits. Codes, verifiers, tokens, account IDs and consent URLs are never printed
or written to disk. Attempts use ephemeral SQLite; restart requires a fresh
flow. Python does not promise cryptographic memory zeroization.

The start page checks exact Host, same-origin POST and a browser cookie at
callback. Its form allows redirect only to the Spotify authorization host.
The start page uses `same-origin` referrer policy so Chrome supplies Origin;
callback/results use `no-referrer`. Provider requests use fixed TLS endpoints,
bounded responses, no automatic redirects/environment proxies and fixed errors.
This browser binding is not a Home Assistant administrator/session binding.

Provider revocation is separate from local credential disposal. Remove the
dedicated test grant through Spotify's account Apps settings when finished;
do not revoke the app used by an existing native HA integration. Revocation,
later invalid-grant behavior and encrypted backup/restore are not proven here.

## Test budget, acceptance and remaining gates

### Live provider result

The owner created a dedicated test app with the exact loopback redirect,
reviewed the consent screen in Chrome and explicitly approved the displayed
read permission. The real Spotify run returned `http_status: 200`,
`result: spotify_pkce_verified`, `profile_verified: true`,
`refresh_verified: true` and `local_credentials_erased: true`. The client
exited after displaying the safe result. No account ID or grant was retained
in this evidence. Provider revocation was not run. Home Assistant actor
binding and the remotely reachable App callback are explicitly unproven.

There are **15 deterministic research-client tests**, supplementing 28 existing
authorization/SQLite/callback tests. Fake transports prove local handling only.

| Boundary | Offline result | Live result |
| --- | --- | --- |
| Exact redirect and minimal scope | Pass | Dedicated-app consent screen reached |
| S256 PKCE | RFC 7636 vector passes | Real code exchange passed |
| Missing/wrong browser cookie | Rejected before exchange | Not separately run |
| Wrong state | Rejected before exchange | Not separately run |
| Expired state | Rejected before exchange | Not separately run |
| Callback replay | At most one exchange | Not separately run |
| Mixed code/error | Rejected before exchange | Not separately run |
| Consent denial | No exchange; transient binding cleared | Not separately run |
| Extra/malformed grant or header injection | Profile blocked | Not separately run |
| Redirected/oversized provider response | Fixed bounded error | Not separately run |
| Profile, refresh and same-account verification | Pass with fake transport | Real profile and immediate refresh passed |
| Omitted replacement refresh token | Accepted; no replacement required | Provider response detail intentionally not retained |
| No retained grant or raw response in result | Canary assertions pass | Safe flags only; client exited |
| Cross-origin start, wrong Host, management path | HTTP rejection | Chrome reaches consent |
| HA actor, remote App callback, durable secrets | Not implemented | Blocked |

Traceability: `SYM-SEC-001`–`SYM-SEC-007` map to PKCE, state/cookie, replay,
secret-canary and cleanup tests; `SYM-SEC-008`–`SYM-SEC-010` map to fixed endpoints,
redirect rejection and route isolation. The lab smoke supplies bounded
`SYM-HA-009` evidence. It does not satisfy the full authorization SDD's 82-case
budget or release gates.

The App's OAuth and connection routes remain absent. Even a successful local
PKCE flow does not establish remote/mobile App topology, Ingress actor binding,
production encrypted secrets, durable refresh/recovery, backup/restore, library
or write capabilities. RG-001/RG-002 and existing blockers remain open. No new
ADR or production contract is introduced by this prototype.
