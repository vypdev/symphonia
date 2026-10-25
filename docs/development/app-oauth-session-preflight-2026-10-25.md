# App callback and Home Assistant session preflight

**Observed:** 2026-10-25. **Work:** [issue #26](https://github.com/vypdev/symphonia/issues/26),
[draft PR #27](https://github.com/vypdev/symphonia/pull/27).
**Status:** isolated research; real App callback and session binding remain unproven.

## Actual installation, inspected in Chrome

The owner authorized using the existing Home Assistant installation for this
preflight. Its About screen reported Home Assistant OS 18.3, Core 2026.10.3,
Supervisor 2026.10.3 and Frontend 20260930.5. The authenticated browser could
open administrator settings and the App store. Symphonia was absent from the
installed Apps list; searching all currently configured App repositories for
Symphonia returned no results. This says nothing about unconfigured repositories
or whether a future artifact could be installed.

The [previous proof](spotify-oauth-proof-2026-10-25.md) already recorded HTTP 404
for `/oauth/callback` and `/api/connections` on the disposable Symphonia App.
The current [runtime handler](../../src/symphonia/runtime/http.py) still has no
authorization endpoints, and [App metadata](../../addon/config.yaml) exposes
Ingress only, with no separate callback port. These are distinct facts from
the owner's installed-App inventory; no request to a nonexistent Symphonia
endpoint on that installation is claimed.

The owner confirmed that no stable HTTPS domain/proxy is currently available
for the App callback and requested an isolated proof plus deployment requirements.
No App, repository, integration, credential, proxy, port, device or automation
was changed on the owner's installation. Browser authentication tokens,
Ingress cookies, user IDs and private instance URLs were not extracted.

## Dated official source findings

This section uses official documentation and versioned upstream source, with
no community implementation treated as a provider guarantee.

| Source | Finding and practical limit |
| --- | --- |
| [Spotify redirect requirements](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri) | The registered URI must match; non-loopback redirects require HTTPS. A literal loopback redirect reaches Chrome's computer. A LAN-only hostname can be a candidate if Chrome can reach it over trusted HTTPS; public Internet exposure is not implied by a browser redirect. |
| [Ingress guide](https://contributors.home-assistant.io/apps/guides/ingress/) | Trust the Supervisor peer, use relative paths, and treat absent identity as unknown. A changing authenticated Ingress path is unsuitable as the registered callback. |
| [Core 2026.10.3 Ingress source](https://github.com/home-assistant/core/blob/2026.10.3/homeassistant/components/hassio/ingress.py) | The Core route forwards to Supervisor and adds Ingress routing metadata. Reaching this route is not proof that a Symphonia callback exists. |
| [Supervisor 2026.10.3 Ingress API](https://github.com/home-assistant/supervisor/blob/2026.10.3/supervisor/api/ingress.py) | Session creation requires a user ID from Core. The proxy validates its Ingress cookie, applies `panel_admin`, removes client-supplied remote-user headers case-insensitively, and sets user ID/name/display-name. No remote-user group or Core login-session identifier is promised by this version's header adaptation. |
| [Supervisor 2026.10.3 session implementation](https://github.com/home-assistant/supervisor/blob/2026.10.3/supervisor/ingress.py) | Ingress has a separate expiring, sliding session. A forwarded user ID alone cannot distinguish two browsers logged in as the same user or prove immediate Core logout/revocation semantics. |

The existing native Spotify integration and My Home Assistant OAuth relay do
not establish App callback ownership. A new Spotify application is not the
missing prerequisite: the dedicated research application can receive an
additional exact redirect after a real HTTPS callback has been selected and
verified. Keep the native integration's registration and grant separate.

## Runnable isolated proof

[The experiment](../../tools/ha_oauth_session_spike.py) uses an ephemeral SQLite
attempt repository, a real HTTP callback listener bound only to `127.0.0.1`
on an allocated port, and synthetic administrator/browser contexts. It never
contacts Spotify or Home Assistant, accepts no client credentials, stores no
real grant and is not an installable App or production authentication adapter.
The reserved `example.test` origins are fixtures, not deployment addresses.

```text
PYTHONPATH=src:. python3 tools/ha_oauth_session_spike.py
PYTHONPATH=src:. python3 -m unittest tests.test_ha_oauth_session_spike -v
```

The callback validates state/provider/exact redirect/attempt metadata and
stages a bounded synthetic code in memory. It does not consume the attempt or
perform even the simulated exchange until completion presents the initiating
actor and a fingerprint of the same synthetic browser nonce through the
trusted-peer/origin fixture. The direct listener ignores forwarded identity
and cookies and has no management routes. Completion consumes once, runs the
fake exchange once, and discards transient references. Denial never exchanges.
Expiry is recorded and pending references are cleared on the next interaction;
process exit abandons the in-memory flow. Python memory zeroization is not promised.

The executable receipt distinguishes its claims explicitly:

```json
{
  "mode": "isolated_simulation",
  "real_home_assistant": "not_run",
  "real_spotify": "not_run",
  "callback_waited_for_session": true,
  "wrong_session_rejected": true,
  "initiating_context_completed": true,
  "exchange_once": true
}
```

There are **22 deterministic tests** in
[the session experiment suite](../../tests/test_ha_oauth_session_spike.py).
They cover staged-before-finalization behavior; another browser of the same
actor; another actor with the same nonce; untrusted peer; wrong origin;
missing/malformed context; wrong state/provider; changed durable redirect,
provider, actor or attempt metadata; callback and finalization expiry at the
deadline; replay; duplicate callbacks; ambiguous/oversized queries; denial;
completion before callback; sanitized exchange failure; concurrent completion;
restart; redacted context representation; real local HTTP route/header
isolation; non-loopback refusal; and the executable receipt.

The passing fixture is evidence for the proposed two-step policy only.
`SyntheticIngressContext` is supplied by tests: treating a browser-supplied
body/header as that context in production would bypass authentication.
Neither an HA session nor an HA administrator was authenticated by this tool.

Verification on this research revision: **431 Python tests passed**, including
the 22 session-experiment tests; combined line/branch coverage remained **89%**
against the unchanged 85% floor. The executable simulation produced the receipt
above. Specification validation, whitespace checks and the manual SDD/catalog
checks passed; both capability statuses and all readiness blockers are unchanged.

## Requirements before a deployment trial

1. **A reviewed research App artifact.** Prepare a separate, identifiable
   experimental artifact with an immutable build revision, no boot auto-start,
   no native integration changes, no real grant persistence, a short run limit,
   and a stop/uninstall procedure. The current tool is deliberately not that
   artifact. Exercise packaging, startup and stop in the disposable Supervisor
   lab before proposing installation on the owner's system.
2. **A callback-only HTTPS route.** Select the hostname/path and trusted TLS
   termination. Chrome on the test network must reach it without bypassing a
   certificate warning. Proxy only the exact callback to the dedicated App
   listener. Deny management, health, assets, completion endpoints, path aliases
   and arbitrary redirect targets there. Keep administration behind Ingress;
   do not publish HA's port or Ingress token as a workaround. Domain ownership,
   certificate delivery and proxy placement remain unresolved.
3. **An actual Ingress identity adapter.** Obtain actor identity only from the
   verified Supervisor peer and require administrator access. Issue an opaque
   App browser session through that boundary with bounded lifetime, `HttpOnly`,
   appropriate `SameSite`/`Secure` attributes, path isolation and CSRF controls.
   Use trusted HTTPS for the HA administrative browser session as well before
   a real-grant trial; the observed local HTTP entry does not establish this.
   Verify cookie behavior in the actual iframe and remote/local browser paths.
   Define separately whether the requirement concerns the App browser session,
   the Supervisor Ingress session, or the Core login session. Immediate Core
   logout/revocation must not be inferred from a user ID or nonce.
4. **A complete bounded flow.** Start through Ingress, bind actor/browser,
   provider, exact HTTPS redirect, PKCE verifier, state, expiry and attempt.
   Receive the callback without management authority, then finalize through
   the initiating authenticated Ingress context. Return no code, token, HA
   credential or Ingress URL to ordinary result pages. Define idle expiry,
   cancellation, restart, concurrent finalization and unknown exchange outcomes.
5. **A reviewed installation and provider registration.** Review the exact
   artifact, permissions, listeners, route and rollback before installing it.
   Register the selected exact HTTPS URI on the dedicated Spotify test app.
   Retain only `user-read-private` for this trial; no Client Secret is needed
   for the PKCE research profile. Keep codes, verifiers and grants off disk,
   logs and evidence. Do not revoke the native Spotify integration's access.

These requirements prepare a research deployment; they do not resolve the
production secret-store, backup, supported-platform or release decisions.
Production implementation still requires the authorization SDD readiness gates
and explicit owner approval. No accepted architecture contract or ADR is changed.

The subsequent [installable trial artifact](ha-oauth-trial-2026-10-25.md)
prepares a separate App, hash-verified source export and opt-in callback-only
Quick Tunnel, with installation/transport evidence in the disposable lab.
Its availability does not turn any pending owner-installation live case into
a pass.

## Required live acceptance matrix

Every row below is **not run** on the owner's installation. A future trial
needs at least **16 distinct live cases**, supplementing the offline suite and
the authorization SDD's unchanged 82-case budget.

| Case | Required observation |
| --- | --- |
| 1. Local HTTPS return | Chrome reaches only the registered App callback with trusted TLS |
| 2. Remote browser return | Same result from the declared remote access path, or explicitly unsupported |
| 3. Initiating administrator | Verified Supervisor identity and initiating App session permit one completion |
| 4. Same user, another browser | Completion fails without consuming the initiating browser's flow |
| 5. Another user | Completion is denied even if callback state is known |
| 6. Non-administrator | Supervisor/App refuses authorization management |
| 7. Missing/expired session | No exchange or connection; fresh flow required |
| 8. Logout/revocation | Named Core/Ingress/App session semantics are observed independently |
| 9. Forged identity | Direct callback headers/cookies cannot acquire management authority |
| 10. Listener isolation | Management, completion and UI routes are denied through the HTTPS callback route |
| 11. CSRF/wrong origin | No authorization start or completion from an unrelated origin |
| 12. State/PKCE/redirect mismatch | No exchange for wrong, duplicate or mismatched correlation |
| 13. Replay/concurrency | Exactly one callback and completion owner; no second exchange |
| 14. Denial/expiry/restart | No connection; transient secrets removed by the documented deadline/recovery |
| 15. Account and refresh | Real minimal-scope exchange, immutable account and one same-account refresh pass |
| 16. Cleanup/redaction | Stop removes transient access; no secret canary in ordinary responses/logs/evidence; provider grant status stated separately |

Traceability: actor/browser/state/expiry/replay and cleanup support
`SYM-SEC-001`–`SYM-SEC-007`; listener/origin/redirect isolation supports
`SYM-SEC-008`–`SYM-SEC-010`; the observed App inventory and versioned Ingress
analysis support bounded research for `SYM-HA-009`. All real App/session and
production readiness claims remain open until their own evidence exists.
